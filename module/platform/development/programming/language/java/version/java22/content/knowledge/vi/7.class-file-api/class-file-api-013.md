# Bài tập thống kê phương thức, sinh lớp đơn giản và kiểm tra lớp sau biến đổi

Class-File API cho phép chương trình Java đọc, tạo và biến đổi file `.class` bằng các mô hình có kiểu. Thay vì tự phân tích byte, tự tính offset hoặc ghi từng bytecode instruction, ta làm việc với `ClassModel`, `MethodModel`, `ClassBuilder`, `CodeBuilder` và các transform. Những công cụ này hữu ích khi xây dựng bộ phân tích bytecode, công cụ kiểm tra chất lượng, bộ sinh mã hoặc plugin xử lý class file.

Class-File API được giới thiệu dưới dạng preview trong JDK 22 (JEP 457), tiếp tục preview trong JDK 23 (JEP 466) và trở thành API chính thức từ JDK 24 (JEP 484). Tại thời điểm JDK 27, package `java.lang.classfile` vẫn thuộc module chuẩn `java.base`; các API dùng trong bài có trạng thái stable và không cần `--enable-preview` hoặc module incubator. Vì vậy, các ví dụ dưới đây dùng API chính thức từ JDK 24 trở lên, đồng thời tương thích với JDK 27.

## 1. Mục tiêu và chuẩn bị

Sau bài thực hành, bạn có thể:

1. Đọc `ClassModel` và thống kê số lượng, loại và trạng thái của các phương thức trong một class file.
2. Dùng `ClassFile.build` và `CodeBuilder` để sinh một lớp Java đơn giản.
3. Dùng `ClassFile.transformClass` và `ClassTransform` để thêm phương thức vào lớp đã có.
4. Dùng `ClassFile.verify` để phát hiện lỗi xác minh, sau đó nạp và gọi lớp đã biến đổi để kiểm tra hành vi ở runtime.

Yêu cầu môi trường: JDK 24 trở lên. Ví dụ dùng API chuẩn trong `java.base`, không cần khai báo dependency bên ngoài và không cần bật preview.

| Mốc | Trạng thái Class-File API | Cấu hình sử dụng |
| --- | --- | --- |
| JDK 22 — JEP 457 | Preview lần đầu | Chỉ dùng khi nghiên cứu mã lịch sử; cần bật preview của JDK 22. |
| JDK 23 — JEP 466 | Preview lần thứ hai | Cần bật preview của JDK 23. |
| JDK 24 — JEP 484 | API chính thức | Không cần preview; package `java.lang.classfile` thuộc `java.base`. |
| JDK 25–27 | API chuẩn | Dùng trực tiếp trong ứng dụng và công cụ Java hiện đại. |

Không nên biên dịch class file preview của JDK 22 rồi dùng lại như artifact bình thường trên JDK mới. Khi nâng cấp dự án từ preview, hãy biên dịch lại từ mã nguồn bằng JDK đích và bỏ `--enable-preview` nếu dự án không còn sử dụng tính năng preview khác.

## 2. Bài tập 1: thống kê phương thức trong một class file

`ClassFile.parse(Path)` đọc file `.class` và trả về `ClassModel`. Từ model này, `methods()` cung cấp danh sách `MethodModel`. Mỗi method model có tên, descriptor, access flags và `code()` để kiểm tra phương thức có thân bytecode hay không.

Các thông tin thường hữu ích khi thống kê:

- Tổng số phương thức được khai báo.
- Số constructor (`<init>`) và class initializer (`<clinit>`).
- Số phương thức `public`, `private`, `protected` và `static`.
- Số phương thức `abstract`, `native` và số phương thức có `Code` attribute.
- Tên và descriptor của từng phương thức.

### Mã thực hành

Tạo file `MethodStatistics.java`:

```java
import java.io.IOException;
import java.lang.classfile.AccessFlag;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;
import java.util.List;

public class MethodStatistics {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java MethodStatistics <class-file>");
            return;
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));
        List<MethodModel> methods = model.methods();

        long constructors = count(methods, "<init>");
        long classInitializers = count(methods, "<clinit>");
        long publicMethods = countFlag(methods, AccessFlag.PUBLIC);
        long privateMethods = countFlag(methods, AccessFlag.PRIVATE);
        long protectedMethods = countFlag(methods, AccessFlag.PROTECTED);
        long staticMethods = countFlag(methods, AccessFlag.STATIC);
        long abstractMethods = countFlag(methods, AccessFlag.ABSTRACT);
        long nativeMethods = countFlag(methods, AccessFlag.NATIVE);
        long methodsWithCode = methods.stream()
                .filter(method -> method.code().isPresent())
                .count();

        System.out.println("Class: " + model.thisClass().asInternalName());
        System.out.println("Major version: " + model.majorVersion());
        System.out.println("Total methods: " + methods.size());
        System.out.println("Constructors: " + constructors);
        System.out.println("Class initializers: " + classInitializers);
        System.out.println("Public: " + publicMethods);
        System.out.println("Private: " + privateMethods);
        System.out.println("Protected: " + protectedMethods);
        System.out.println("Static: " + staticMethods);
        System.out.println("Abstract: " + abstractMethods);
        System.out.println("Native: " + nativeMethods);
        System.out.println("Methods with Code: " + methodsWithCode);

        System.out.println("\nMethod details:");
        for (MethodModel method : methods) {
            System.out.printf("%s %s flags=%s hasCode=%s%n",
                    method.methodName().stringValue(),
                    method.methodType().stringValue(),
                    method.flags().flags(),
                    method.code().isPresent());
        }
    }

    private static long count(List<MethodModel> methods, String name) {
        return methods.stream()
                .filter(method -> method.methodName().stringValue().equals(name))
                .count();
    }

    private static long countFlag(List<MethodModel> methods, AccessFlag flag) {
        return methods.stream()
                .filter(method -> method.flags().has(flag))
                .count();
    }
}
```

Biên dịch và chạy:

```bash
javac MethodStatistics.java
java MethodStatistics path/to/SomeClass.class
```

`methodType()` trả về descriptor ở dạng chuỗi, ví dụ `(Ljava/lang/String;I)Z`. `flags().has(AccessFlag.STATIC)` kiểm tra một access flag mà không cần tự thao tác bit mask. `code().isPresent()` phân biệt phương thức có thân bytecode với các phương thức không có `Code` attribute như abstract hoặc native method.

Lưu ý khi đọc kết quả:

- `<init>` là constructor của instance; `<clinit>` là class initializer do compiler tạo khi lớp cần khởi tạo static.
- Một số method được compiler sinh thêm, ví dụ bridge hoặc synthetic method. Nếu thống kê chỉ muốn phản ánh API mà lập trình viên khai báo, cần lọc thêm `AccessFlag.BRIDGE` và `AccessFlag.SYNTHETIC`.
- Các nhóm thống kê có thể chồng lấp. Một phương thức `public static` được tính vào cả nhóm public và static; không cộng các nhóm này để suy ra tổng số phương thức.
- `Code` attribute có thể không tồn tại với abstract/native method. Không nên giả định mọi method đều có bytecode để duyệt.

### Bài tập mở rộng

1. Thêm thống kê số phương thức có `synchronized`, `final`, `bridge` và `synthetic` flag.
2. In riêng các phương thức public nhưng không static để tìm instance API của lớp.
3. Chỉ đếm method không phải constructor và không phải synthetic.
4. Duyệt `CodeModel` để đếm instruction nếu cần phân tích độ phức tạp bytecode; phân biệt `Instruction` với pseudo instruction dùng cho nhãn và thông tin debug.

## 3. Bài tập 2: sinh một lớp đơn giản bằng ClassBuilder

Để sinh class file, dùng `ClassFile.of().build(ClassDesc, handler)`. Handler nhận `ClassBuilder`, từ đó khai báo access flags, superclass, field và method. Với method có thân, `withMethodBody` nhận tên, `MethodTypeDesc`, access flags và một `CodeBuilder` handler.

Ví dụ tiếp theo sinh lớp `lab.GeneratedAnswer` có một phương thức `public static int answer()` trả về `42`.

### Mã thực hành

Tạo file `GenerateClass.java`:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;

public class GenerateClass {
    public static void main(String[] args) throws IOException {
        ClassFile classFile = ClassFile.of();
        ClassDesc className = ClassDesc.of("lab.GeneratedAnswer");

        byte[] bytes = classFile.build(className, builder -> builder
                .withVersion(ClassFile.JAVA_24_VERSION, 0)
                .withFlags(ClassFile.ACC_PUBLIC
                        | ClassFile.ACC_FINAL
                        | ClassFile.ACC_SUPER)
                .withSuperclass(ClassDesc.of("java.lang.Object"))
                .withMethodBody(
                        "answer",
                        MethodTypeDesc.ofDescriptor("()I"),
                        ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                        code -> code.loadConstant(42).ireturn()));

        Path output = Path.of("build/generated/lab/GeneratedAnswer.class");
        Files.createDirectories(output.getParent());
        Files.write(output, bytes);

        System.out.println("Generated: " + output.toAbsolutePath());
        System.out.println("Class bytes: " + bytes.length);
    }
}
```

Biên dịch và chạy bằng JDK 24 trở lên:

```bash
javac GenerateClass.java
java GenerateClass
```

Lớp được tạo có class file version 68 (Java 24) nhờ `withVersion(ClassFile.JAVA_24_VERSION, 0)`. Cách đặt version tường minh giúp công cụ chạy trên JDK mới vẫn sinh artifact cho phiên bản đích đã chọn, thay vì vô tình phát hành class file với major version mới nhất của runtime. Nếu muốn target JDK 25, 26 hoặc 27, hãy chọn hằng version tương ứng và bảo đảm runtime triển khai hỗ trợ version đó.

`loadConstant(42)` phát một hằng số int lên operand stack, còn `ireturn()` trả int về caller. `CodeBuilder` tự chọn instruction phù hợp để mã hóa hằng và tạo phần code cần thiết; không cần tự ghi opcode hay tính độ dài bytecode.

Lớp ví dụ chỉ có phương thức static nên không khai báo constructor. Class file không bắt buộc phải có constructor; lớp này có thể được nạp và gọi các phương thức static nhưng không thể khởi tạo bằng `new` nếu không có constructor phù hợp.

Có thể kiểm tra nhanh class file được sinh bằng công cụ JDK:

```bash
javap -p -c build/generated/lab/GeneratedAnswer.class
```

Kết quả cần thể hiện method `public static int answer()` với bytecode nạp giá trị 42 rồi trả về.

### Bài tập mở rộng

1. Thêm method `public static String label()` trả về chuỗi `"generated"` bằng `loadConstant("generated")` và `areturn()`.
2. Thêm field `public static final int VERSION` và `ConstantValue` attribute phù hợp.
3. Sinh hai method có descriptor khác nhau, sau đó dùng bài tập 1 để thống kê class file vừa tạo.
4. Thử đặt class file version về JDK 25 và quan sát major version trong kết quả thống kê.

## 4. Bài tập 3: biến đổi lớp và kiểm tra sau biến đổi

`ClassFile.transformClass(ClassModel, ClassTransform)` tạo class file mới từ model đầu vào. Transform có thể chuyển tiếp phần tử cũ, bỏ phần tử hoặc thêm phần tử mới. `ClassTransform.endHandler` hữu ích khi muốn giữ nguyên nội dung đã duyệt và thêm một thành phần ở cuối quá trình transform.

Trong bài này, ta đọc `GeneratedAnswer.class`, thêm method `public static int twiceAnswer()` trả về `84`, xác minh byte array mới bằng `ClassFile.verify`, parse lại và nạp lớp để gọi method vừa thêm.

### Mã thực hành

Tạo file `TransformAndVerify.java`:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class TransformAndVerify {
    public static void main(String[] args)
            throws IOException, ReflectiveOperationException {
        ClassFile classFile = ClassFile.of();
        Path input = Path.of("build/generated/lab/GeneratedAnswer.class");
        Path output = Path.of("build/transformed/lab/GeneratedAnswer.class");

        ClassModel original = classFile.parse(input);

        byte[] transformed = classFile.transformClass(
                original,
                ClassTransform.endHandler(builder -> builder.withMethodBody(
                        "twiceAnswer",
                        MethodTypeDesc.ofDescriptor("()I"),
                        ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                        code -> code.loadConstant(84).ireturn())));

        List<VerifyError> errors = classFile.verify(transformed);
        if (!errors.isEmpty()) {
            errors.forEach(System.err::println);
            throw new IllegalStateException("Generated class has verification errors");
        }

        ClassModel transformedModel = classFile.parse(transformed);
        boolean methodExists = transformedModel.methods().stream()
                .anyMatch(method -> method.methodName()
                        .stringValue().equals("twiceAnswer"));
        if (!methodExists) {
            throw new IllegalStateException("twiceAnswer was not added");
        }

        Files.createDirectories(output.getParent());
        Files.write(output, transformed);

        Class<?> generatedClass = new GeneratedClassLoader().define(transformed);
        int answer = (int) generatedClass.getMethod("answer").invoke(null);
        int twiceAnswer = (int) generatedClass.getMethod("twiceAnswer").invoke(null);

        if (answer != 42 || twiceAnswer != 84) {
            throw new AssertionError("Unexpected method result");
        }

        System.out.println("Verification: PASS");
        System.out.println("answer() = " + answer);
        System.out.println("twiceAnswer() = " + twiceAnswer);
        System.out.println("Transformed class: " + output.toAbsolutePath());
    }

    static final class GeneratedClassLoader extends ClassLoader {
        Class<?> define(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }
}
```

Chạy sau khi đã hoàn thành bài tập 2:

```bash
javac TransformAndVerify.java
java TransformAndVerify
```

Kết quả mong đợi:

```text
Verification: PASS
answer() = 42
twiceAnswer() = 84
```

Ở đây có ba mức kiểm tra khác nhau:

1. **Kiểm tra cấu trúc bằng `ClassFile.verify`.** API trả về danh sách `VerifyError`; danh sách rỗng nghĩa là không tìm thấy lỗi xác minh trong class file theo các kiểm tra của API.
2. **Đọc lại bằng `ClassFile.parse`.** Xác nhận class file mới có method `twiceAnswer` và có thể truy cập metadata sau transform.
3. **Nạp và gọi bằng JVM.** `GeneratedClassLoader` định nghĩa class từ byte array, sau đó reflection gọi hai method static và kiểm tra kết quả thực tế.

Không nên xem `verify()` là bằng chứng duy nhất rằng class chắc chắn chạy đúng trong mọi môi trường. Lỗi liên kết với dependency, class loader, quyền truy cập hoặc hành vi logic có thể chỉ xuất hiện khi nạp hay thực thi. Với công cụ sinh và transform bytecode, nên kết hợp kiểm tra class file, kiểm tra API sau parse và test runtime trên JDK đích.

### Bài tập mở rộng

1. Thay vì thêm method mới, biến đổi method `answer()` để trả về `100` và kiểm tra kết quả sau khi nạp lớp.
2. Chỉ biến đổi method có tên `answer`, giữ nguyên các method còn lại bằng `ClassTransform.transformingMethods` hoặc `ClassTransform.transformingMethodBodies`.
3. Thử tạo method có descriptor sai với bytecode trả về, quan sát lỗi khi build hoặc verify.
4. Thử thêm tham chiếu tới một class không có trong runtime class path để phân biệt lỗi xác minh cấu trúc với lỗi liên kết khi thực thi.

## 5. Cách chọn đúng API trong một công cụ Class-File

| Nhu cầu | API chính |
| --- | --- |
| Đọc file class từ đường dẫn | `ClassFile.parse(Path)` |
| Duyệt metadata lớp | `ClassModel` |
| Duyệt method, descriptor và flags | `ClassModel.methods()`, `MethodModel` |
| Tạo class file mới | `ClassFile.build(ClassDesc, Consumer)` |
| Tạo thân method | `ClassBuilder.withMethodBody`, `CodeBuilder` |
| Biến đổi class đã parse | `ClassFile.transformClass`, `ClassTransform` |
| Biến đổi riêng method hoặc code | `ClassTransform.transformingMethods`, `ClassTransform.transformingMethodBodies`, `MethodTransform`, `CodeTransform` |
| Kiểm tra class file | `ClassFile.verify(byte[])`, `verify(ClassModel)` hoặc `verify(Path)` |

Class-File API mô hình hóa các thành phần class file bằng những đối tượng bất biến và builder có kiểu. Hãy dùng descriptor và factory method của API để mô tả lớp, method và instruction; tránh tự nối byte hoặc hard-code constant pool index khi không có yêu cầu đặc biệt. Khi transform, chỉ thay đổi phần tử cần thiết và để API xử lý việc tái tạo các cấu trúc liên quan như constant pool, offset và stack map.

## 6. Tóm tắt thực hành

- Dùng `ClassModel` và `MethodModel` để phân tích class file, không cần tự đọc cấu trúc nhị phân.
- Dùng `AccessFlag` để đọc access flags có kiểu; dùng `methodType()` để lấy descriptor.
- Dùng `ClassFile.build`, `ClassBuilder` và `CodeBuilder` để tạo class file mới.
- Dùng `ClassFile.transformClass` và `ClassTransform` để biến đổi class file hiện có.
- Dùng `ClassFile.verify` trước khi ghi hoặc nạp byte array mới, sau đó kiểm tra lại bằng parse và runtime test.
- Trên JDK 24 trở lên, Class-File API là API stable; không cần preview flag hoặc incubator module.

## Tài liệu tham khảo

- [JEP 457: Class-File API (Preview)](https://openjdk.org/jeps/457) — lần preview đầu tiên trong JDK 22.
- [JEP 466: Class-File API (Second Preview)](https://openjdk.org/jeps/466) — lần preview thứ hai trong JDK 23.
- [JEP 484: Class-File API](https://openjdk.org/jeps/484) — hoàn thiện API trong JDK 24.
- [ClassFile, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html) — parse, build, transform, verify và class file version.
- [ClassModel, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassModel.html) — mô hình lớp và danh sách method.
- [MethodModel, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/MethodModel.html) — tên, descriptor, flags và code của method.
- [ClassBuilder, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassBuilder.html) — xây dựng lớp và method.
- [CodeBuilder, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeBuilder.html) — tạo bytecode instruction.
- [ClassTransform, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassTransform.html) — biến đổi thành phần lớp.
- [Java SE 27 API: java.lang.classfile](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/package-summary.html) — package Class-File API chính thức.
