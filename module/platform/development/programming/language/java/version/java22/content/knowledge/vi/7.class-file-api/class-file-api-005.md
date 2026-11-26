# Sinh lớp, trường và phương thức bằng builder với mô tả kiểu hợp lệ

Class-File API cho phép tạo cấu trúc bytecode `.class` trực tiếp từ Java. Thay vì tự ghép byte, constant pool và các thuộc tính theo đặc tả JVM, ta mô tả lớp bằng builder: khai báo tên lớp, lớp cha, trường, phương thức, descriptor và các lệnh bytecode cần thiết.

Khi tạo class file, phần mô tả kiểu phải chính xác. JVM không lưu kiểu Java dưới dạng tên viết trong mã nguồn; nó dùng **field descriptor** cho trường và **method descriptor** cho phương thức. Class-File API kết hợp hai kiểu mô tả danh định `ClassDesc` và `MethodTypeDesc` để giảm lỗi khi tạo các descriptor này.

Class-File API được giới thiệu ở Java 22 dưới dạng preview (JEP 457), tiếp tục preview ở Java 23 (JEP 466), và trở thành API chính thức trong Java 24 qua JEP 484. Nội dung và ví dụ dưới đây dùng API ổn định từ JDK 24 trở lên; không cần bật `--enable-preview`.

## 1. Các builder tạo nên một class file

API nằm trong package `java.lang.classfile`, thuộc module `java.base`. Các builder chính tương ứng với những phần cấu trúc của file `.class`:

| Builder | Nhiệm vụ |
|---|---|
| `ClassBuilder` | Khai báo tên lớp, access flags, lớp cha, interface, trường và phương thức. |
| `FieldBuilder` | Cấu hình một trường, gồm access flags và các attribute gắn với trường. |
| `MethodBuilder` | Cấu hình phương thức và các attribute của phương thức. |
| `CodeBuilder` | Sinh các lệnh bytecode cho phần thân phương thức. |

Thông thường, không tự khởi tạo các builder. Ta gọi `ClassFile.of().build(...)`; API truyền `ClassBuilder` vào lambda. Từ builder lớp, ta thêm field và method. Với phương thức có thân, `withMethodBody(...)` cung cấp trực tiếp `CodeBuilder` để tạo bytecode.

Một pipeline sinh class file cơ bản:

```text
ClassFile.of().build(ClassDesc, classBuilder -> ...)
                         |
                         +-- withFlags(...)
                         +-- withSuperclass(...)
                         +-- withField(...)
                         +-- withMethodBody(...)
                                  |
                                  +-- CodeBuilder instructions
                         |
                         +-- byte[] class file
```

Thứ tự các phần tử cấp lớp không phải lúc nào cũng quyết định ý nghĩa như thứ tự lệnh trong thân phương thức. Riêng `CodeBuilder`, thứ tự gọi các phương thức như `aload`, `getfield`, `ireturn` chính là thứ tự bytecode được sinh ra.

## 2. Mô tả kiểu bằng `ClassDesc`

`ClassDesc` là mô tả danh định cho một kiểu đơn, được dùng cho tên lớp, kiểu trường, kiểu trả về hoặc kiểu tham số riêng lẻ.

Với kiểu tham chiếu, dùng tên nhị phân đầy đủ, phân cách package bằng dấu chấm:

```java
ClassDesc personType = ClassDesc.of("demo.Person");
ClassDesc stringType = ClassDesc.of("java.lang.String");
```

Với kiểu nguyên thủy, nên dùng các hằng trong `ConstantDescs`:

```java
ClassDesc intType = ConstantDescs.CD_int;
ClassDesc booleanType = ConstantDescs.CD_boolean;
ClassDesc voidType = ConstantDescs.CD_void;
```

Không dùng `ClassDesc.of("int")` để mô tả `int`; cách đó coi `int` là tên một lớp. Có thể dùng `ClassDesc.ofDescriptor("I")`, nhưng hằng `ConstantDescs.CD_int` rõ ràng và dễ đọc hơn.

Một số field descriptor JVM thường gặp:

| Kiểu Java | Field descriptor |
|---|---|
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

`ClassDesc.descriptorString()` trả về chuỗi descriptor tương ứng. Với kiểu lớp, `ClassDesc.of("demo.Person")` biểu diễn kiểu nhị phân `demo.Person`; khi chuyển thành descriptor JVM, dấu chấm trong tên lớp được đổi thành dấu gạch chéo và được bao bởi `L` cùng dấu `;`.

## 3. Mô tả chữ ký phương thức bằng `MethodTypeDesc`

`MethodTypeDesc` mô tả toàn bộ chữ ký của một phương thức: kiểu trả về và danh sách kiểu tham số. Có thể tạo bằng `MethodTypeDesc.of(returnType, parameterTypes...)`:

```java
ClassDesc stringType = ClassDesc.of("java.lang.String");
ClassDesc intType = ConstantDescs.CD_int;
ClassDesc voidType = ConstantDescs.CD_void;

MethodTypeDesc constructorType = MethodTypeDesc.of(
    voidType,
    intType,
    stringType
);

MethodTypeDesc getterType = MethodTypeDesc.of(intType);
MethodTypeDesc convertType = MethodTypeDesc.of(stringType, intType);
```

Điểm dễ nhầm: trong lời gọi `MethodTypeDesc.of`, kiểu trả về đứng trước, sau đó mới đến các tham số. Trong chuỗi method descriptor của JVM, thứ tự là `(<các tham số>)<kiểu trả về>`.

| Chữ ký Java | Method descriptor |
|---|---|
| `void run()` | `()V` |
| `int getId()` | `()I` |
| `String name(int id)` | `(I)Ljava/lang/String;` |
| `void set(int id, String name)` | `(ILjava/lang/String;)V` |
| `String[] values(int[] ids)` | `([I)[Ljava/lang/String;` |

Vì thế, `constructorType` ở trên có `descriptorString()` là `(ILjava/lang/String;)V`. Constructor trong class file luôn có tên đặc biệt `<init>` và kiểu trả về `void`.

Không được dùng `void` làm kiểu trường hoặc kiểu tham số. `MethodTypeDesc.of(...)` từ chối kiểu tham số là `void`. Với trường, `ClassDesc` phải mô tả một kiểu trường hợp lệ theo JVM; `void` chỉ xuất hiện ở vị trí kiểu trả về của method descriptor.

## 4. Khai báo lớp và trường bằng `ClassBuilder`

Ví dụ sẽ sinh lớp `demo.Person` có hai trường `id` và `name`:

```java
ClassDesc personType = ClassDesc.of("demo.Person");
ClassDesc stringType = ClassDesc.of("java.lang.String");

byte[] bytes = ClassFile.of().build(personType, classBuilder ->
    classBuilder
        .withFlags(ClassFile.ACC_PUBLIC)
        .withSuperclass(ConstantDescs.CD_Object)
        .withField("id", ConstantDescs.CD_int, ClassFile.ACC_PRIVATE)
        .withField("name", stringType, ClassFile.ACC_PRIVATE)
);
```

Các thành phần:

- `ClassDesc.of("demo.Person")` xác định tên lớp sẽ được ghi vào class file.
- `withFlags(ClassFile.ACC_PUBLIC)` đặt access flag cho lớp.
- `withSuperclass(ConstantDescs.CD_Object)` khai báo `java.lang.Object` là lớp cha trực tiếp.
- `withField(name, descriptor, flags)` khai báo một trường cùng kiểu và access flags.

`withField` có overload nhận lambda `FieldBuilder` khi cần cấu hình thêm attribute của trường. Nếu chỉ cần tên, kiểu và access flags, overload nhận `int flags` là đủ.

Các access flags thường dùng gồm `ACC_PUBLIC`, `ACC_PRIVATE`, `ACC_PROTECTED`, `ACC_STATIC` và `ACC_FINAL`. Flag phải phù hợp với vị trí khai báo: flag của lớp, trường và phương thức có các quy tắc khác nhau.

Khai báo một trường không đồng nghĩa với việc gán giá trị ban đầu cho nó. Trường instance thường được gán trong constructor `<init>`; trường static thường được khởi tạo trong phương thức `<clinit>`. Nếu cần giá trị hằng theo quy tắc class file, có thể thêm `ConstantValue` attribute phù hợp thay vì nhầm lẫn giữa khai báo field và mã khởi tạo.

## 5. Sinh constructor, getter và phương thức static

Một method cần có descriptor phù hợp với bytecode được sinh. Ví dụ, constructor nhận `int id` và `String name`, gọi constructor của `Object`, rồi ghi hai tham số vào trường tương ứng.

```java
import java.lang.classfile.ClassFile;
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class GeneratePersonClass {
    private static final ClassDesc PERSON = ClassDesc.of("demo.Person");
    private static final ClassDesc STRING = ClassDesc.of("java.lang.String");
    private static final ClassDesc INT = ConstantDescs.CD_int;
    private static final ClassDesc VOID = ConstantDescs.CD_void;
    private static final ClassDesc OBJECT = ConstantDescs.CD_Object;

    private static final MethodTypeDesc CONSTRUCTOR =
        MethodTypeDesc.of(VOID, INT, STRING);
    private static final MethodTypeDesc GET_ID = MethodTypeDesc.of(INT);
    private static final MethodTypeDesc GET_NAME = MethodTypeDesc.of(STRING);
    private static final MethodTypeDesc NEXT_ID = MethodTypeDesc.of(INT, INT);

    public static void main(String[] args) throws Exception {
        ClassFile classFile = ClassFile.of();

        byte[] classBytes = classFile.build(PERSON, classBuilder ->
            classBuilder
                .withVersion(ClassFile.JAVA_24_VERSION, 0)
                .withFlags(ClassFile.ACC_PUBLIC)
                .withSuperclass(OBJECT)

                .withField("id", INT, ClassFile.ACC_PRIVATE)
                .withField("name", STRING, ClassFile.ACC_PRIVATE)

                // public Person(int id, String name)
                .withMethodBody("<init>", CONSTRUCTOR, ClassFile.ACC_PUBLIC,
                    code -> code
                        .aload(0)
                        .invokespecial(OBJECT, "<init>", ConstantDescs.MTD_void)
                        .aload(0)
                        .iload(1)
                        .putfield(PERSON, "id", INT)
                        .aload(0)
                        .aload(2)
                        .putfield(PERSON, "name", STRING)
                        .return_())

                // public int getId()
                .withMethodBody("getId", GET_ID, ClassFile.ACC_PUBLIC,
                    code -> code
                        .aload(0)
                        .getfield(PERSON, "id", INT)
                        .ireturn())

                // public String getName()
                .withMethodBody("getName", GET_NAME, ClassFile.ACC_PUBLIC,
                    code -> code
                        .aload(0)
                        .getfield(PERSON, "name", STRING)
                        .areturn())

                // public static int nextId(int current)
                .withMethodBody("nextId", NEXT_ID,
                    ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                    code -> code
                        .iload(0)
                        .iconst_1()
                        .iadd()
                        .ireturn())
        );

        List<VerifyError> errors = classFile.verify(classBytes);
        if (!errors.isEmpty()) {
            throw new IllegalStateException(errors.toString());
        }

        Path classPath = Path.of("out", "demo", "Person.class");
        Files.createDirectories(classPath.getParent());
        Files.write(classPath, classBytes);

        System.out.println("Generated: " + classPath);
    }
}
```

Chạy chương trình tạo class file bằng JDK 24 trở lên:

```bash
javac GeneratePersonClass.java
java GeneratePersonClass
javap -p -s -classpath out demo.Person
```

`javap -p -s` hiển thị thành viên và descriptor. Kết quả có dạng tương tự:

```text
public class demo.Person {
  private int id;
    descriptor: I
  private java.lang.String name;
    descriptor: Ljava/lang/String;
  public demo.Person(int, java.lang.String);
    descriptor: (ILjava/lang/String;)V
  public int getId();
    descriptor: ()I
  public java.lang.String getName();
    descriptor: ()Ljava/lang/String;
  public static int nextId(int);
    descriptor: (I)I
}
```

Trong ví dụ, `withVersion(ClassFile.JAVA_24_VERSION, 0)` chủ động đặt class file target ở định dạng Java 24. Nếu bỏ lời gọi này, Class-File API dùng phiên bản mặc định của context. Chỉ đặt một phiên bản mục tiêu mà runtime đích có thể nạp.

## 6. Đọc từng lệnh bytecode trong ví dụ

`CodeBuilder` cung cấp các phương thức tương ứng với instruction JVM. Ví dụ constructor dùng:

| Lệnh | Ý nghĩa |
|---|---|
| `aload(0)` | Đẩy tham chiếu `this` từ local variable slot 0 lên operand stack. |
| `invokespecial(Object, "<init>", MTD_void)` | Gọi constructor không tham số của lớp cha. |
| `iload(1)` | Đọc tham số `id` từ slot 1. |
| `aload(2)` | Đọc tham số `name` từ slot 2. |
| `putfield(...)` | Ghi giá trị trên operand stack vào trường của đối tượng. |
| `return_()` | Kết thúc phương thức trả về `void`. |

Slot bắt đầu từ 0. Với phương thức instance, slot 0 dành cho `this`; các tham số tiếp theo bắt đầu từ slot 1. Với phương thức static không có `this`, tham số đầu tiên bắt đầu ở slot 0. `long` và `double` chiếm hai local variable slots; các kiểu còn lại trong ví dụ chiếm một slot.

Các getter sử dụng `getfield` để đọc trường. `ireturn` trả về giá trị dạng `int`, còn `areturn` trả về tham chiếu. Phương thức static `nextId` không đọc `this`; nó lấy tham số ở slot 0, đẩy hằng số 1, cộng bằng `iadd`, rồi trả kết quả bằng `ireturn`.

Với `withMethodBody`, bit `ACC_STATIC` phải được đặt trong `methodFlags` truyền vào builder. Không thể chờ tới lambda `MethodBuilder` để thay đổi trạng thái static của method. Nếu cần thêm các attribute của method ngoài `Code`, dùng `withMethod(...)` và cấu hình qua `MethodBuilder`.

## 7. Vì sao descriptor và bytecode phải khớp nhau?

Descriptor là hợp đồng kiểu mà JVM dùng khi liên kết và gọi thành viên. Bytecode trong thân phương thức phải tuân thủ hợp đồng đó.

Ví dụ, nếu method được khai báo với descriptor `()I`, thân phương thức phải kết thúc bằng lệnh trả về kiểu int tương ứng. Nếu descriptor khai báo một tham số `String`, bytecode phải đọc tham số ở local slot phù hợp và sử dụng nó như một tham chiếu. Nếu đánh dấu method là static nhưng lại viết bytecode truy cập `this`, method sẽ không có receiver hợp lệ.

Một số lỗi thường gặp:

| Lỗi | Nguyên nhân | Cách tránh |
|---|---|---|
| Dùng `ClassDesc.of("int")` | Mô tả `int` như tên một lớp. | Dùng `ConstantDescs.CD_int`. |
| Dùng `ClassDesc` cho toàn bộ chữ ký method | Thiếu danh sách tham số và cấu trúc method descriptor. | Dùng `MethodTypeDesc`. |
| Đặt kiểu trả về cuối khi gọi `MethodTypeDesc.of` | Nhầm thứ tự API với chuỗi descriptor JVM. | Truyền kiểu trả về trước, các kiểu tham số sau. |
| Dùng `void` làm tham số hoặc field | Không hợp lệ theo định dạng descriptor JVM. | Chỉ dùng `void` làm kiểu trả về method/constructor. |
| Đặt sai access flags | Field hoặc method mang flag không phù hợp. | Dùng đúng `ClassFile.ACC_*` tại vị trí khai báo. |
| Method descriptor và lệnh return không khớp | Ví dụ method trả `String` nhưng dùng `ireturn`. | Đảm bảo `areturn`, `ireturn`, `lreturn`, `freturn`, `dreturn` hoặc `return_` phù hợp với kiểu trả về. |
| Đọc sai local variable slot | Quên slot `this` hoặc slot kép của `long`/`double`. | Tính slot theo loại method và kiểu tham số; có thể dùng `CodeBuilder.parameterSlot(...)`. |
| Ghi field bằng giá trị sai kiểu | Operand stack không có kiểu phù hợp với field descriptor. | Khớp `putfield`/`putstatic` với descriptor của field. |

## 8. Descriptor hợp lệ không đồng nghĩa class file đã hoàn toàn đúng

`ClassDesc` và `MethodTypeDesc` giúp tạo descriptor có cú pháp hợp lệ. Tuy nhiên, Class-File API không tự thực hiện mọi kiểm tra nhất quán ngữ nghĩa ngay khi builder nhận dữ liệu. Một số mâu thuẫn nghiêm trọng trong bytecode có thể chỉ lộ ra khi xây dựng, xác minh hoặc nạp class file.

Vì vậy, sau khi sinh byte array, có thể dùng `ClassFile.verify(...)` để yêu cầu API xác minh class file:

```java
List<VerifyError> errors = ClassFile.of().verify(classBytes);
if (errors.isEmpty()) {
    System.out.println("Class file passed verification");
} else {
    errors.forEach(System.err::println);
}
```

Danh sách rỗng nghĩa là không phát hiện lỗi xác minh class file trong phạm vi verifier. Nó không thay thế kiểm tra lúc nạp/link class, kiểm tra các dependency có tồn tại trong class loader đích, hoặc kiểm thử hành vi của mã được sinh. Với class file tham chiếu tới kiểu ngoài JDK hoặc kiểu chỉ có trong class loader riêng, có thể cần cấu hình `ClassHierarchyResolverOption` phù hợp để API phân tích hierarchy khi sinh stack map hoặc xác minh.

Một điểm nữa: JVM descriptor lưu kiểu đã xóa generic (erasure). Ví dụ trường `List<String>` có field descriptor `Ljava/util/List;`. Nếu cần giữ thông tin generic cho reflection và công cụ đọc chữ ký, phải thêm `Signature` attribute tương ứng; descriptor trường vẫn là kiểu đã xóa generic.

## 9. Khi nào dùng builder và khi nào dùng descriptor thô?

Với mã sinh class file mới, ưu tiên API danh định:

- `ClassDesc.of(...)` cho kiểu tham chiếu.
- `ConstantDescs.CD_*` cho các kiểu nguyên thủy và kiểu nền tảng phổ biến.
- `ClassDesc.arrayType()` cho kiểu mảng.
- `MethodTypeDesc.of(...)` cho chữ ký phương thức.
- `ClassBuilder.withField(...)` và `withMethodBody(...)` để thêm thành viên.

`ClassDesc.ofDescriptor(...)` và `MethodTypeDesc.ofDescriptor(...)` vẫn hữu ích khi đọc hoặc chuyển đổi descriptor có sẵn từ một công cụ khác. Khi tự tạo cấu trúc mới, tránh ghép chuỗi descriptor bằng tay vì rất dễ nhầm dấu `;`, dấu `/`, dấu ngoặc hoặc kiểu trả về.

## 10. Kết luận

Để sinh lớp, trường và phương thức bằng Class-File API, hãy bắt đầu từ `ClassFile.of().build(...)`, dùng `ClassDesc` để mô tả kiểu đơn và `MethodTypeDesc` để mô tả chữ ký phương thức. `ClassBuilder` khai báo class, superclass, fields và methods; `CodeBuilder` sinh lệnh bytecode có thứ tự.

Descriptor phải khớp với access flags, local variable slots, operand stack và lệnh return trong method body. Sau khi build, dùng `ClassFile.verify(...)`, rồi tiếp tục kiểm tra việc nạp và chạy class file trong môi trường đích. API chính thức từ Java 24 trở đi không yêu cầu bật preview.

## Tài liệu tham khảo

- [JEP 484 – Class-File API (Java 24)](https://openjdk.org/jeps/484)
- [JEP 466 – Class-File API (Second Preview, Java 23)](https://openjdk.org/jeps/466)
- [JEP 457 – Class-File API (Preview, Java 22)](https://openjdk.org/jeps/457)
- [Package `java.lang.classfile` – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html)
- [ClassBuilder – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassBuilder.html)
- [CodeBuilder – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [ClassFile – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [ClassDesc – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/constant/ClassDesc.html)
- [MethodTypeDesc – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/constant/MethodTypeDesc.html)
