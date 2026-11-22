# Ứng dụng trong compiler và thư viện sinh bytecode — hằng số động Java 11

**Hằng số động** (*dynamic class-file constant*, thường gọi là **condy**) là cơ chế JVM được đưa vào **Java 11 qua JEP 309**. Nó bổ sung entry **`CONSTANT_Dynamic`, tag 17** trong constant pool của class file phiên bản **55**. Thay vì luôn ghi giá trị cuối cùng vào constant pool, compiler hoặc thư viện sinh bytecode ghi **mô tả để JVM gọi một bootstrap method tạo ra giá trị khi hằng số được resolve**.

Tính năng này phù hợp cho **compiler backend, language runtime, bytecode transformer, instrumentation, dynamic class generation**. Nó không thêm một cú pháp Java source mới như `dynamic const` và cũng không biến mọi biến `final` thành dynamic constant.

**Nguyên tắc chính:** hằng số được *tính động tại resolution* nhưng kết quả được **cache theo symbolic reference của runtime constant pool**. Nó không phải getter chạy lại mỗi khi code đọc giá trị. Bootstrap phải có contract rõ, tránh side effect nghiệp vụ và phải an toàn trước tình huống nhiều thread cùng resolve.

Bài này chỉ dùng kiến thức vẫn áp dụng trên JDK hiện đại. Mã mẫu được biên dịch bằng `javac --release 11` và thư viện **OW2 ASM 9.11.1** được phát hành vào tháng 10/2026. ASM là API bytecode công khai, khác package nội bộ `jdk.internal.org.objectweb.asm` không nên phụ thuộc.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả `CONSTANT_Dynamic` và lý do compiler/language runtime cần nó.
2. Phân biệt dynamic constant với literal, `static final`, `<clinit>` và `invokedynamic`.
3. Hiểu `BootstrapMethods`, `CONSTANT_MethodHandle`, `CONSTANT_NameAndType`, tên và field descriptor.
4. Nêu đúng bootstrap signature với `MethodHandles.Lookup`, `String`, `Class<?>` cùng static arguments.
5. Giải thích thời điểm resolution, cache giá trị, cache lỗi và bootstrap concurrency.
6. Dùng `ConstantBootstraps` Java 11 hoặc viết bootstrap riêng khi cần.
7. Sinh class file với `ClassWriter`, `Handle`, `ConstantDynamic` và `visitLdcInsn` của ASM.
8. Dùng `javap -v` xác minh class-file version 55, dynamic entries và bootstrap.
9. Thiết kế IR/compiler emission, lựa chọn sử dụng condy hợp lý và bảo toàn nó khi bytecode transformation.
10. Nhận diện các lỗi `BootstrapMethodError`, type mismatch, class loader, cycles và input bytecode không đáng tin.

## 2. Vì sao compiler cần một loại constant mới?

Constant pool truyền thống chứa được các literal như `String`, số, symbolic class references, method handles và method types. Nhưng một compiler có thể muốn nhúng **một giá trị tham chiếu được tạo ở runtime theo ngữ cảnh class loader hoặc class được liên kết**, ví dụ:

- Một instance của enum được xác định bởi tên và enum type.
- Một `VarHandle` trỏ đến field/array có kiểm tra quyền truy cập.
- Một bảng lookup bất biến, được snapshot theo phiên của generated class.
- Một đối tượng biểu diễn metadata chỉ resolve được khi runtime đã biết type.
- Một giá trị có thể tạo một lần khi cần, thay vì khởi tạo sớm trong `<clinit>`.

Trước condy, compiler thường phát mã helper, static field và initializer riêng hoặc tính lại trong method. Java 11 cho phép biểu diễn giá trị thành một entry trong constant pool và chuyển việc link cho JVM:

```text
Compiler / bytecode generator
        |
        | ConstantDynamic(name, descriptor, bootstrap, arguments)
        v
CONSTANT_Dynamic trong class file
        |
        | bytecode ldc / ldc_w / ldc2_w
        v
JVM resolve constant:
    1. Resolve bootstrap method handle và arguments
    2. Tạo Lookup, name, Class type
    3. Invoke bootstrap
    4. Kiểm tra kiểu kết quả
    5. Lưu resolution
        |
        v
Lần dùng tiếp theo: lấy cùng kết quả đã resolve
```

Đây là **late linking của một hằng**, không phải “hằng số thay đổi mỗi lần gọi”.

## 3. Cấu trúc `CONSTANT_Dynamic`

Theo Java Virtual Machine Specification (JVMS) `4.4.10:

```text
CONSTANT_Dynamic_info {
    u1 tag;                         // 17
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
```

Đây là **pseudo-structure của định dạng class file**, không phải chương trình Java.

- `tag = 17` phân biệt dynamic constant với literal và `invokedynamic`.
- `bootstrap_method_attr_index` chỉ tới một entry của thuộc tính `BootstrapMethods`.
- `name_and_type_index` chỉ tới `CONSTANT_NameAndType`, trong đó descriptor là **field descriptor**, ví dụ `Ljava/lang/String;` hoặc `I`.
- `BootstrapMethods` lưu tham chiếu `CONSTANT_MethodHandle` và zero hoặc nhiều static arguments hợp lệ.
- Static args có thể là những hằng được JVM chấp thuận, kể cả dynamic constants khác. **Không được tạo chu kỳ tự tham chiếu**.

Ví dụ một entry dùng trong bài:

```text
name: ENTRY
descriptor: Ljava/lang/String;
bootstrap: CondyAsmLab.bootstrap
static arguments: "item-", 7
```

Ở bytecode, method chỉ cần một `ldc` phù hợp để nạp giá trị. Mặc dù trong file có tên `ENTRY`, Java source không bắt buộc có field thật tên `ENTRY`.

### Tag, version và lệnh nạp

| Thành phần | Giá trị | Giải thích |
| --- | --- | --- |
| `CONSTANT_Dynamic` | **tag 17** | Dynamic constant |
| `CONSTANT_InvokeDynamic` | tag 18 | Dynamic call site |
| Java 11 class-file version | **55.0** | Yêu cầu JVM hỗ trợ class version 55 |
| `ldc` / `ldc_w` | Nạp hằng kiểu `int`, `float`, reference... | Index pool một/two-byte |
| `ldc2_w` | Nạp `long` hoặc `double` | Wide primitive với hai slot |
| `BootstrapMethods` | Class attribute | Tập bootstrap specs |
| `CONSTANT_NameAndType` | Name + field descriptor | Xác định tên và kiểu hằng |

**Không dùng class version 52 (Java 8) với tag 17**; runtime Java 8 cũng không load được class version 55. Khi target là Java 11, chọn `Opcodes.V11` của ASM.

## 4. Condy khác `invokedynamic` như thế nào?

Hai cơ chế có chung ý tưởng bootstrap nhưng mang ý nghĩa khác nhau:

| So sánh | `CONSTANT_Dynamic` | `invokedynamic` |
| --- | --- | --- |
| Đối tượng được liên kết | **Một giá trị** | **Một lời gọi** |
| Type trong `NameAndType` | Field descriptor (`Ljava/lang/String;`, `J`) | Method descriptor (`(I)Ljava/lang/String;`) |
| Tham số type của bootstrap | `Class<?>` | `MethodType` |
| Kết quả bootstrap | Giá trị tương thích descriptor, có thể `null` với reference | `CallSite` hợp lệ, không được `null` |
| Lệnh sử dụng | `ldc`/`ldc_w`/`ldc2_w` | `invokedynamic` |
| Ứng dụng | Giá trị late-bound | Liên kết invocation (ví dụ dynamic language call site) |

Không nhầm `ConstantBootstraps` với `LambdaMetafactory`: helper cho dynamic constant không phải công cụ tạo `CallSite`. Với condy, bootstrap thông thường có ba tham số đầu **`MethodHandles.Lookup`, `String`, `Class<?>`**; với invokedynamic tham số thứ ba là **`MethodType`**.

## 5. Vòng đời resolution và cache

Theo JVMS `5.4.3.6, một symbolic reference chưa được resolve cho dynamic constant được resolve khi JVM phải sử dụng nó, chẳng hạn chạy `ldc` hoặc dùng nó làm static argument cho bootstrap khác.

```text
Class đã được define
       |
       +-- Method chứa ldc chưa chạy
       |       -> Condy có thể chưa được resolve
       |
       +-- Lần đầu đi tới ldc
               -> Resolve handle, descriptor và static arguments
               -> Gọi bootstrap
               -> Validate kiểu
               -> Lưu kết quả hoặc lỗi
               |
               +-- Các lần sau cùng reference
                       -> Dùng kết quả/lỗi đã được lưu
```

**Cache theo runtime constant-pool reference, không theo tên string.** Hai class khác loaders, hoặc hai entries khác nhau trong cùng class, không tự chia sẻ cache chỉ vì cùng tên `"ENTRY"`.

### Bootstrap có được gọi đúng một lần không?

**Không được bảo đảm theo nghĩa side effect khi có concurrency.** JVM có thể cho nhiều thread đang tranh resolve cùng một entry **gọi bootstrap đồng thời**. Một kết quả được chọn làm resolution chính thức, những kết quả đua còn lại không dùng.

Điều này có nghĩa:

- Bootstrap nên là phép tính **deterministic**, càng ít side effects càng tốt.
- Không đặt thao tác thanh toán, gửi email, cấp ID giao dịch hay update global state không an toàn vào bootstrap.
- Nếu có shared state, áp dụng đồng bộ hóa/thread-safety.
- Test tuần tự có thể thấy một lần gọi, nhưng **không** đặt invariant “bootstrap counter luôn bằng 1 trong mọi thử nghiệm concurrency”.

### Nếu bootstrap bị lỗi thì sao?

Nếu resolution thất bại do bootstrap ném exception thông thường, JVM có thể báo **`BootstrapMethodError`**. Lỗi resolution theo symbolic reference cũng được nhớ: lần dùng tiếp theo của reference này không đơn thuần gọi lại bootstrap như một retry.

Vì vậy, **không dùng condy cho dữ liệu phải thử lại từ mạng** hoặc feature flags đổi liên tục. Khi cần thay config mà không reload class, dùng state holder/service hoặc API có vòng đời riêng.

### Có thể resolve `null` không?

Có, cho **reference type**. Java 11 có `ConstantBootstraps.nullConstant`. Với primitive descriptor `I` hay `J`, `null` không phải một kết quả hợp lệ.

## 6. Bootstrap method: chữ ký và kiểu dữ liệu

Một bootstrap đơn giản có thể viết:

```java
public static String bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String prefix,
        int number) {
    if (type != String.class) {
        throw new IllegalArgumentException("Unexpected type");
    }
    return prefix + number;
}
```

Đây là **method minh họa đặt trong một public class**, cần import `java.lang.invoke.MethodHandles`; không có `main`.

| Đối số | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `lookup` | JVM | Lookup context của class chứa constant, với access constraints |
| `name` | `CONSTANT_NameAndType` | Tên constant, ví dụ `ENTRY` |
| `type` | Field descriptor | `Class` đại diện kiểu giá trị cần tạo |
| `prefix` | Bootstrap static arg | Dữ liệu compile-time của compiler |
| `number` | Bootstrap static arg | Một số nguyên do generator cung cấp |

Bootstrap không tự có quyền đọc private của mọi module. `Lookup` phản ánh bối cảnh caller hợp lệ; Java module access và method handle permissions vẫn được JVM kiểm tra.

Type descriptor phải đúng với kết quả. Bootstrap trả `Integer` nhưng descriptor `Ljava/lang/String;` không được JVM “tự stringify”. Một type mismatch có thể dẫn tới `BootstrapMethodError`.

**Static args không phải Java objects tuỳ ý**: các giá trị được biểu diễn qua những constant-pool forms hợp lệ. Không thể đưa một live `Socket`, `Thread` hoặc arbitrary instance vào `BootstrapMethods` như thể class file lưu trực tiếp object trên heap.

## 7. Những ứng dụng thực tế trong compiler

### 7.1. Compiler cho ngôn ngữ JVM

Một compiler backend có thể biểu diễn trong IR:

```text
Expression
  |
  +-- LiteralConstant(value, type)
  |
  +-- DynamicConstant(name, fieldDescriptor,
  |                   bootstrapHandle, staticArguments)
  |
  +-- RuntimeExpression(instructions)
```

Khi compile:

1. **Literal** như `42` hoặc `"hello"`: dùng constant bình thường.
2. **Late-bound nhưng ổn định theo class loader**: cân nhắc condy.
3. **Kết quả cần tính ở mỗi request**: dùng method/bytecode runtime.
4. **Operation có side effect**: không đặt logic vào bootstrap.

Ví dụ enum instance hoặc `VarHandle` có thể được linked từ runtime class/type metadata. Tuy vậy, không phải mọi enum/VarHandle usage đều nhất thiết cần condy: compiler phải cân nhắc chi phí, kiểu target và khả năng tối ưu hóa.

### 7.2. Giảm helper method và static initializer

Khi một compiler muốn đưa một object bất biến vào class, nó có thể tránh sinh một field `static final` rồi thêm code `<clinit>` để khởi tạo. Condy cho phép giữ mô tả giá trị ở constant pool và tính khi cần.

Không nên hứa tăng hiệu năng theo một con số: `static final`, JIT và lazy linkage có đặc điểm khác nhau. Ưu điểm chính là **mô hình biểu diễn/linking gọn và phù hợp với constant-pool semantics**.

### 7.3. Giá trị theo class-loader identity

Một compiler/plugin runtime chạy trong nhiều class loaders có thể muốn constant dùng đúng `Class<?>` và quyền của generated class. Bootstrap dùng `lookup.lookupClass()` để biết caller, thay vì lấy một giá trị đã được tính trong JVM của build tool.

Nhưng cùng binary name không đồng nghĩa cùng class identity nếu class loaders khác nhau. Không tạo global cache dựa vào mỗi chuỗi class name khi kết quả cần phân biệt loader.

### 7.4. Constant folding đúng chỗ

Nếu biểu thức thực sự tính được tại compile time và không phụ thuộc runtime, hãy fold thành literal thường. Nếu cần resolution theo type/loader của JVM, condy có thể là lựa chọn tốt hơn việc embed build-time object hoặc lặp lại helper.

### 7.5. Instrumentation và generated runtime

Bytecode library dùng condy để giữ một reference/configuration bất biến của generated code có thể đơn giản hơn fields và getters. Nhưng không được dùng để “đóng băng” API key/secret đang phải rotate hoặc trạng thái nghiệp vụ có yêu cầu reload. Cached object **vẫn có thể mutable**; condy cache reference chứ không biến object thành immutable.

## 8. `ConstantBootstraps` trong Java 11

Java 11 cung cấp `java.lang.invoke.ConstantBootstraps` với các bootstrap có sẵn:

| Phương thức | Ý nghĩa |
| --- | --- |
| `nullConstant` | Tạo một `null` reference constant |
| `primitiveClass` | Lấy `Class` của primitive type |
| `enumConstant` | Resolve enum instance theo tên và kiểu |
| `getStaticFinal` | Lấy static final field phù hợp với access rules |
| `invoke` | Invoke method handle để tạo constant |
| `fieldVarHandle` | Resolve `VarHandle` của instance field |
| `staticFieldVarHandle` | Resolve `VarHandle` của static field |
| `arrayVarHandle` | Resolve `VarHandle` của array |

Các helper này giảm công viết bootstrap riêng nhưng **không nới quyền truy cập**. `enumConstant` có thể lỗi nếu enum name không có; `getStaticFinal` có thể lỗi khi field không tồn tại, không final hoặc không được phép truy cập.

**Đừng dùng API ra đời muộn trong source target Java 11.** Các lớp thuộc `java.lang.constant` như `DynamicConstantDesc` và `ConstantDescs` có từ **Java 12 (JEP 334)**, không có trong Java 11. Trong bài này, **ASM `org.objectweb.asm.ConstantDynamic`** là class của thư viện ngoài, không phải `java.lang.constant.DynamicConstantDesc`.

## 9. Chọn công cụ sinh bytecode

Việc viết trực tiếp cấu trúc constant pool, BootstrapMethods, Code attributes, stack frames và offset bằng mảng byte rất dễ hỏng. Nên dùng library/API được bảo trì:

| Công cụ | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| **OW2 ASM** | Bytecode visitor và generator cấp thấp, hỗ trợ `ConstantDynamic` trực tiếp | Cần hiểu descriptors, frames và verifier |
| **Byte Buddy** | Sinh class/instrumentation ở mức trừu tượng cao hơn | Kiểm tra tính năng và version phù hợp mục tiêu |
| **Standard Class-File API** (`java.lang.classfile`) | API chuẩn JDK từ Java 24 (JEP 484) | **Không có trong Java 11** |
| Tự viết class file bytes | Hữu ích để nghiên cứu JVMS | Không khuyến nghị production |
| `jdk.internal.org.objectweb.asm` | **Không nên sử dụng** | Internal API không ổn định, bị encapsulation |

Tính đến **07/11/2026**, bản **OW2 ASM 9.11.1** đã phát hành. Với Maven:

```xml
<dependency>
    <groupId>org.ow2.asm</groupId>
    <artifactId>asm</artifactId>
    <version>9.11.1</version>
</dependency>
```

Đây là một **đoạn dependency** đặt trong `<dependencies>` của `pom.xml`; không phải dự án Maven đầy đủ. Chỉ core artifact `asm` là đủ cho ví dụ dưới đây. Trong production nên quản lý dependency bằng Maven/Gradle, khóa version và theo dõi security updates, thay vì dùng một JAR tự tải không được kiểm soát.

## 10. Ví dụ hoàn chỉnh: sinh `CONSTANT_Dynamic` bằng ASM

Chúng ta sẽ tạo một chương trình **`CondyAsmLab.java`**, dùng ASM để sinh class `CondyTarget` với các method static:

- `first` và `again` cùng dùng condy `ENTRY`.
- `other` dùng condy riêng `OTHER`.
- `broken` và `brokenAgain` cùng dùng condy `BROKEN` có bootstrap cố ý ném lỗi.
- `empty` dùng `ConstantBootstraps.nullConstant`.

Sau khi ghi class file, chương trình load nó bằng custom `ClassLoader`, gọi method qua reflection và in số lượt bootstrap. Toàn bộ logic chạy được với Java 11 API + OW2 ASM 9.11.1.

Tạo file **`CondyAsmLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.ConstantDynamic;
import org.objectweb.asm.Handle;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class CondyAsmLab {
    private static final AtomicInteger BOOTSTRAP_CALLS =
            new AtomicInteger();

    public static String bootstrap(
            MethodHandles.Lookup caller,
            String name, Class<?> type, String prefix, int number) {
        BOOTSTRAP_CALLS.incrementAndGet();
        if (type != String.class) {
            throw new IllegalArgumentException("unexpected type");
        }
        if ("BROKEN".equals(name)) {
            throw new IllegalArgumentException("invalid bootstrap argument");
        }
        return prefix + number + "@" + caller.lookupClass().getSimpleName();
    }

    private static void emitMethod(
            ClassWriter writer, String methodName, ConstantDynamic value) {
        MethodVisitor mv = writer.visitMethod(
                Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                methodName, "()Ljava/lang/String;", null, null);
        mv.visitCode();
        mv.visitLdcInsn(value);
        mv.visitInsn(Opcodes.ARETURN);
        mv.visitMaxs(1, 0);
        mv.visitEnd();
    }

    private static byte[] generate() {
        ClassWriter writer = new ClassWriter(0);
        writer.visit(Opcodes.V11, Opcodes.ACC_PUBLIC | Opcodes.ACC_SUPER,
                "CondyTarget", null, "java/lang/Object", null);

        Handle bootstrap = new Handle(
                Opcodes.H_INVOKESTATIC, "CondyAsmLab", "bootstrap",
                "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;"
                + "Ljava/lang/String;I)Ljava/lang/String;", false);

        ConstantDynamic primary = new ConstantDynamic(
                "ENTRY", "Ljava/lang/String;", bootstrap,
                "item-", Integer.valueOf(7));
        ConstantDynamic another = new ConstantDynamic(
                "OTHER", "Ljava/lang/String;", bootstrap,
                "other-", Integer.valueOf(9));
        ConstantDynamic broken = new ConstantDynamic(
                "BROKEN", "Ljava/lang/String;", bootstrap,
                "bad-", Integer.valueOf(0));

        Handle nullBootstrap = new Handle(
                Opcodes.H_INVOKESTATIC,
                "java/lang/invoke/ConstantBootstraps", "nullConstant",
                "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;",
                false);
        ConstantDynamic nullValue = new ConstantDynamic(
                "EMPTY", "Ljava/lang/String;", nullBootstrap);

        emitMethod(writer, "first", primary);
        emitMethod(writer, "again", primary);
        emitMethod(writer, "other", another);
        emitMethod(writer, "broken", broken);
        emitMethod(writer, "brokenAgain", broken);
        emitMethod(writer, "empty", nullValue);
        writer.visitEnd();
        return writer.toByteArray();
    }

    private static final class LocalLoader extends ClassLoader {
        LocalLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(byte[] bytes) {
            return defineClass("CondyTarget", bytes, 0, bytes.length);
        }
    }

    private static Object call(Class<?> target, String name)
            throws Exception {
        return target.getMethod(name).invoke(null);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Output directory path required");
        }
        byte[] bytes = generate();
        Files.write(Path.of(args[0]).resolve("CondyTarget.class"), bytes);
        Class<?> target = new LocalLoader(
                CondyAsmLab.class.getClassLoader()).define(bytes);

        System.out.println("Bootstrap calls before first ldc: " +
                BOOTSTRAP_CALLS.get());
        System.out.println("First value: " + call(target, "first"));
        System.out.println("Bootstrap calls after first: " +
                BOOTSTRAP_CALLS.get());
        System.out.println("Same condy again: " + call(target, "again"));
        System.out.println("Bootstrap calls after same condy: " +
                BOOTSTRAP_CALLS.get());
        System.out.println("Different condy: " + call(target, "other"));
        System.out.println("Bootstrap calls after other: " +
                BOOTSTRAP_CALLS.get());
        System.out.println("Null condy is null: " +
                (call(target, "empty") == null));

        for (String name : new String[] {"broken", "brokenAgain"}) {
            try {
                call(target, name);
                System.out.println("Unexpected success");
            } catch (InvocationTargetException exception) {
                System.out.println(name + " failed: " +
                        exception.getCause().getClass().getSimpleName());
            }
        }
        System.out.println("Bootstrap calls at end: " +
                BOOTSTRAP_CALLS.get());
    }
}
```

### 10.1. Biên dịch/chạy trên Linux hoặc macOS

```sh
curl -fL -o asm-9.11.1.jar https://repo.maven.apache.org/maven2/org/ow2/asm/asm/9.11.1/asm-9.11.1.jar
javac --release 11 -encoding UTF-8 -cp asm-9.11.1.jar CondyAsmLab.java
java -cp ".:asm-9.11.1.jar" CondyAsmLab .
```

Đường dẫn `.` là thư mục ghi `CondyTarget.class`. Ở Linux/macOS, classpath separator là `:`.

### 10.2. Biên dịch/chạy bằng PowerShell trên Windows

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://repo.maven.apache.org/maven2/org/ow2/asm/asm/9.11.1/asm-9.11.1.jar" -OutFile "asm-9.11.1.jar"

javac --release 11 -encoding UTF-8 -cp ".\asm-9.11.1.jar" CondyAsmLab.java
java -cp ".;.\asm-9.11.1.jar" CondyAsmLab .
```

Windows dùng `;` làm classpath separator. Trong production, nên dùng dependency manager thay vì tải JAR thủ công.

### 10.3. Stdout chính xác

```text
Bootstrap calls before first ldc: 0
First value: item-7@CondyTarget
Bootstrap calls after first: 1
Same condy again: item-7@CondyTarget
Bootstrap calls after same condy: 1
Different condy: other-9@CondyTarget
Bootstrap calls after other: 2
Null condy is null: true
broken failed: BootstrapMethodError
brokenAgain failed: BootstrapMethodError
Bootstrap calls at end: 3
```

**Đã kiểm thử:** `javac --release 11` với ASM 9.11.1 biên dịch thành công; JDK chạy chương trình và in đúng các dòng trên. `javap -v` cũng xác nhận generated class có major version 55, `Dynamic`, `BootstrapMethods` và `ldc`.

### 10.4. Tại sao những kết quả này quan trọng?

**Count = 0 trước `ldc`.** Tạo `ConstantDynamic` ở generator và define `CondyTarget.class` chỉ tạo metadata; bootstrap chưa nhất thiết chạy.

**`first` làm count = 1.** JVM resolve `ENTRY`, gửi `name="ENTRY"`, `type=String.class`, static args `"item-"` và `7`. `caller.lookupClass()` cho biết generated class là `CondyTarget`, nên kết quả `item-7@CondyTarget`.

**`again` giữ count = 1.** Hai method cùng phát `ldc` tham chiếu một dynamic constant entry và reuse kết quả resolution. Không phải “mỗi method một lần bootstrap”.

**`other` làm count = 2.** `OTHER` là một entry khác, bootstrap chạy lần đầu riêng và trả `other-9@CondyTarget`.

**`empty` trả `null`.** `ConstantBootstraps.nullConstant` xử lý hằng reference hợp lệ; không tăng counter của bootstrap tùy chỉnh.

**`broken` làm count = 3.** Bootstrap ném `IllegalArgumentException`, JVM wrap lỗi thành `BootstrapMethodError`. `Method.invoke` wrap lỗi trong `InvocationTargetException` nên mã ví dụ đọc `exception.getCause()`.

**`brokenAgain` không tăng count.** Resolution failure của cùng entry được nhớ; gọi tiếp không có nghĩa tự tính lại.

**Giới hạn test:** các lệnh thực thi là tuần tự, nên cho kết quả counter chính xác như trên. Khi nhiều thread tranh resolution lần đầu, bootstrap có thể bị gọi đồng thời; do đó không thiết kế side effects dựa trên con số counter của demo.

### 10.5. Ý nghĩa các API ASM trong mã

- `ClassWriter` viết class file; `writer.visit(Opcodes.V11, ...)` đặt version Java 11.
- `Handle` với `H_INVOKESTATIC` mô tả tham chiếu tới public static bootstrap, đồng bộ owner/name/descriptor.
- `new ConstantDynamic(...)` tạo object metadata cho constant-pool dynamic entry, **chưa tạo kết quả cuối**.
- `visitLdcInsn(value)` yêu cầu ASM phát bytecode nạp hằng đó.
- `visitMaxs(1,0)` phù hợp **với method cực ngắn chỉ push một reference rồi return**, không copy giá trị này cho method phức tạp.
- `LocalLoader.define` định nghĩa class trong một class loader riêng; runtime pool và resolution thuộc class đã được define.
- Trong ví dụ không tạo instance của `CondyTarget` nên generated class không cần public constructor; nếu sinh ứng dụng bình thường, cần định nghĩa constructor/methods theo hợp đồng tương ứng.

## 11. Dùng `javap -v` để xem constant pool

Sau khi chạy `CondyAsmLab`, file `CondyTarget.class` có thể được xem:

```sh
javap -v -p CondyTarget
```

Nếu file ở thư mục khác, thêm `-classpath` trỏ tới thư mục chứa class file.

Các dấu hiệu cần thấy:

```text
major version: 55
...
Dynamic #...:ENTRY:Ljava/lang/String;
Dynamic #...:OTHER:Ljava/lang/String;
Dynamic #...:BROKEN:Ljava/lang/String;
Dynamic #...:EMPTY:Ljava/lang/String;
...
BootstrapMethods:
    ... REF_invokeStatic CondyAsmLab.bootstrap
        arguments: "item-", 7
    ... REF_invokeStatic java.lang.invoke.ConstantBootstraps.nullConstant
...
public static java.lang.String first();
    ldc #...  // Dynamic ENTRY:Ljava/lang/String;
    areturn
```

Đây là **trích yếu minh họa**, không phải output nguyên văn có index ổn định. `javap` thường hiển thị nhiều chi tiết khác; số index/cách render tùy JDK.

Chỉ nhìn `javap` chứng minh class file **có metadata condy**. Nó không chứng minh bootstrap đã được invoke — phải **chạy phương thức dùng `ldc`** mới quan sát resolution. Hãy kiểm tra cả cấu trúc bytecode và hành vi.

## 12. Đọc/biến đổi condy bằng bytecode visitor

Khi viết thư viện phân tích bytecode, `MethodVisitor.visitLdcInsn` có thể nhận `ConstantDynamic`, không chỉ `String`, `Integer`, `Long`, `Type`...

Ví dụ một phần của class kế thừa `MethodVisitor`:

```java
@Override
public void visitLdcInsn(Object value) {
    if (value instanceof ConstantDynamic) {
        ConstantDynamic dynamic = (ConstantDynamic) value;
        String name = dynamic.getName();
        String descriptor = dynamic.getDescriptor();
        Handle bootstrap = dynamic.getBootstrapMethod();
        int count = dynamic.getBootstrapMethodArgumentCount();
        // Kiểm tra metadata; không chạy bootstrap khi chỉ đang phân tích.
    }
    super.visitLdcInsn(value);
}
```

Đây **chỉ là snippet phương thức**, cần phần còn lại của class visitor và import ASM, không thể copy như một file Java độc lập. Khi transform:

1. Không biến `ConstantDynamic` thành một literal placeholder.
2. Preserve bootstrap handle và args khi không đổi semantics.
3. Nếu rename class/method/type, update owner/descriptor/static args đồng bộ.
4. Kiểm tra nested dynamic constants, tránh cycle.
5. Phát lại class file với version đúng.
6. Verify result bằng JVM bytecode verifier và test runtime.

**Không tự invoke bootstrap khi bytecode scanning.** Bootstrap là code thực thi; một analyzer chỉ đọc metadata không được tạo side effects hoặc load class không đáng tin để “biết giá trị cuối”.

## 13. `static final`, `<clinit>`, `invokedynamic` và condy

| Cơ chế | Giá trị được tạo ra sao? | Ý nghĩa |
| --- | --- | --- |
| Literal `ldc "hello"` | String literal/constant pool thông thường | Dữ liệu đã biết |
| `static final int X = 7` | Compile-time constant, có thể inline | Hằng số Java source |
| `static final Foo F = new Foo()` | Code trong `<clinit>` | Khởi tạo field khi class initialization |
| **`CONSTANT_Dynamic`** | Bootstrap tại runtime resolution | Hằng late-bound, sau đó cache |
| `invokedynamic` | Bootstrap liên kết một `CallSite` | Hành vi lời gọi động |
| Method bình thường | Thực thi mỗi lần được gọi | Giá trị cần biến đổi theo thời gian |

**Không tự coi code `static final` nào cũng thành condy.** `javac --release 11` không tự chuyển mọi constant expression của Java thành dynamic constant. Quyết định phát condy thuộc về compiler/bytecode generator.

Condy thường hữu ích khi value là runtime-linked constant; một ứng dụng CRUD thông thường không cần phải dùng nó để thay `static final` hoặc factory method.

## 14. Các trường hợp KHÔNG nên dùng condy

- **Feature flag/remote config thay đổi liên tục:** resolution cache khiến nó không tự refresh.
- **Secret key/credential cần rotation:** cached reference không có chu kỳ cập nhật bảo mật phù hợp.
- **Mọi operation có side effect:** bootstrap không cam kết exactly-once invocation về mặt concurrency.
- **Payment/order creation:** không dùng linkage để thực hiện nghiệp vụ.
- **Code bắt buộc chạy trên JVM cũ hơn 11:** class version 55 không được hỗ trợ.
- **Value phụ thuộc mỗi request/user/session:** dùng runtime computation, không phải một cache theo class constant.
- **Đối tượng mutable được chia sẻ không kiểm soát:** cache reference không tự làm object immutable.
- **Third-party bytecode không đáng tin:** phân tích metadata mà không load/execute.
- **Trường hợp một literal đơn giản đã đủ:** condy không phải tối ưu hóa bắt buộc.

## 15. Kiểm soát lỗi, quyền truy cập và tính tương thích

### `BootstrapMethodError` và các lỗi khác

Condy resolution có thể thất bại do:

- Bootstrap method handle không thể resolve.
- Bootstrap có signature/arguments không tương thích.
- Bootstrap throw một exception khi chạy.
- Giá trị trả về không convert được thành kiểu field descriptor.
- Static argument class không load được hoặc có cycle.
- Class loader/module visibility không đúng.
- Bytecode version/stack/descriptor hỏng.

Một số lỗi xuất hiện dưới dạng `BootstrapMethodError`, nhưng **không phải mọi lỗi liên kết đều nhất thiết bị wrap thành loại này**. Có thể gặp `NoClassDefFoundError`, `IllegalAccessError`, `VerifyError`, `UnsupportedClassVersionError` hoặc `StackOverflowError` tùy nguyên nhân.

**Không retry cùng constant-pool entry để mong bootstrap chạy lại sau failure.** Runtime đã ghi nhận resolution error cho reference đó. Sửa generated class/metadata/bootstrap và kiểm thử lại bằng class definition/loader phù hợp.

### Class loader và module

Bootstrap được gọi với `Lookup` gắn với class chứa symbolic reference. Một generated class ở plugin loader có thể không nhìn thấy bootstrap owner nếu dependency nằm ở loader khác. Cần xem:

- Bootstrap owner và method có accessible từ context generated class không?
- Package/internal class names trong `Handle` đúng không?
- Method descriptor có đúng `Lookup`, `String`, `Class` và args không?
- Module reads/exports và class loader delegation có phù hợp không?
- Có vô tình dùng private/package-private bootstrap từ runtime package khác không?

Không dùng `--add-opens` hay JDK internal reflective bypass như biện pháp mặc định để xử lý class loader lỗi.

### Đồng thời và bất biến

Khi bootstrap có side effect, nhiều thread có thể chạy cùng một bootstrap trước khi JVM chốt giá trị resolution. Hãy ưu tiên pure function/deterministic result, hoặc dùng synchronization và idempotent initialization riêng nếu cần.

Nếu bootstrap trả `ArrayList`, object vẫn có thể bị sửa: chỉ **reference** là kết quả constant, không phải trạng thái object tự động trở thành immutable. Thường nên trả object bất biến hoặc có API read-only.

### Chu kỳ static dynamic arguments

Nếu A dùng B làm static argument, B lại dùng A, resolution cycle không hợp lệ và có thể gây `StackOverflowError`. Compiler có thể phát hiện cycle trong IR trước khi sinh bytecode; đừng để JVM là nơi duy nhất phát hiện lỗi đầu vào compiler.

## 16. Bảng QA cho compiler/ASM và thử nghiệm sản phẩm

| Test | Kết quả mong đợi |
| --- | --- |
| Target Java 11 | Generated class `major version: 55` |
| Dùng `ConstantDynamic` | Constant pool có `Dynamic` entry tag 17 |
| Bootstrap handle/args | `BootstrapMethods` đúng owner, descriptor và static args |
| Chưa chạy method chứa `ldc` | Bootstrap chưa bị gọi trong demo |
| Hai method dùng chung entry | Lần dùng tiếp nhận lại kết quả đã resolve |
| Hai entries khác | Resolution độc lập |
| Bootstrap chuẩn `nullConstant` | Reference constant có thể là `null` |
| Bootstrap throw `IllegalArgumentException` | JVM báo `BootstrapMethodError` theo contract |
| Dùng lại failed reference | Không tính lại bootstrap theo retry |
| Bootstrap trả sai kiểu | Resolution bị từ chối |
| Condy kiểu `long` hoặc `double` | Dùng `ldc2_w`, stack type phù hợp |
| Nested condy static args | Dependencies resolve hợp lệ và không cycle |
| Hai class loaders khác | Runtime identities và caches độc lập |
| Concurrent first use | Không dựa vào invocation counter luôn bằng 1 |
| Bytecode visitor gặp `ConstantDynamic` | Preserve metadata và remap đúng |
| JVM 8 chạy class version 55 | Không hỗ trợ |
| Bootstrap không visible theo module/loader | Lỗi được báo, không bypass access checks |
| Input class file không tin cậy | Chỉ parse metadata, không execute bootstrap |

Để QA đầy đủ, kết hợp:
- **Unit test compiler IR**: type check, valid descriptors và dependency graph.
- **Bytecode inspection**: `javap -v` hoặc ASM `ClassReader`.
- **Runtime linkage test**: define/load class và gọi method.
- **Negative tests**: sai type, invalid bootstrap handle, cycle, class loader conflict.
- **Concurrency tests**: bootstrap thread-safe và kết quả được cache nhất quán.
- **Build validation**: bytecode verifier, artifact packaging, các JVM target.

## 17. Các lỗi hiểu sai thường gặp

1. **“Condy là biến động theo mỗi lần đọc.”** Sai: dynamic ở resolution, giá trị đã resolve được cache.
2. **“Condy và invokedynamic đều trả CallSite.”** Sai: chỉ invokedynamic dùng CallSite.
3. **“Bootstrap condy nhận MethodType.”** Sai: tham số thứ ba thường là `Class<?>`; MethodType dành cho call site.
4. **“Cùng tên ENTRY là cùng constant cache.”** Sai: cache theo runtime constant-pool reference.
5. **“Một bootstrap luôn được gọi exactly once.”** Sai khi có thread race.
6. **“Resolution failure retry sẽ phục hồi.”** Sai: symbolic reference đã fail tiếp tục fail.
7. **“Condy tự giữ object bất biến.”** Sai: cached reference có thể trỏ tới mutable object.
8. **“Có thể đặt mọi object Java vào static args.”** Sai: chỉ những constant-pool forms hợp lệ.
9. **“Java 11 có `java.lang.constant.DynamicConstantDesc`.”** Sai: API này tới từ Java 12.
10. **“Source `static final` đương nhiên sinh condy.”** Sai: compiler/bytecode library phải phát entry.
11. **“Java 8 chạy được class condy nếu dùng ASM mới.”** Sai: JVM phải hiểu class-file version và tag.
12. **“Thư viện có thể dùng JDK internal ASM.”** Không khuyến nghị: internal API không được hỗ trợ ổn định.
13. **“`visitLdcInsn` chỉ nhận primitive/string.”** Sai: có `ConstantDynamic`.
14. **“`javap` cho thấy bootstrap đã chạy.”** Sai: nó chỉ xem metadata.
15. **“Có thể đặt payment operation vào bootstrap.”** Sai: không bảo đảm side-effect exactly-once.
16. **“Dùng condy để refresh environment variable.”** Sai: resolution cache không tự cập nhật.
17. **“Không cần check descriptor/frames vì ASM tạo tự động.”** Sai: generator phải bảo đảm type/verifier constraints.
18. **“Condy có thể vượt private/module access.”** Sai: JVM vẫn kiểm tra quyền.
19. **“Nested condy cycle chỉ là một cảnh báo.”** Sai: có thể làm resolution thất bại nghiêm trọng.
20. **“Cứ bootstrap trả null cho mọi type là được.”** Sai: `null` chỉ hợp lệ cho reference type.

## 18. Bài tập thực hành

**Bài 1 — Đọc bytecode:** Chạy `CondyAsmLab.java`, xem `javap -v -p CondyTarget`. Chỉ ra `tag=17`, `BootstrapMethods`, `ldc` và type descriptor của `ENTRY`.

**Bài 2 — Cache theo entry:** Giải thích vì sao `first` và `again` không tăng counter thêm, nhưng `other` có. Thay một static arg của `another` và quan sát result.

**Bài 3 — Lỗi bootstrap:** Gọi `broken` hai lần rồi đọc count. Vì sao không nên retry một symbolic reference đã resolve lỗi? Chú ý `InvocationTargetException` chỉ là wrapper do reflection.

**Bài 4 — Kiểu kết quả:** Đổi descriptor từ `Ljava/lang/String;` sang `Ljava/lang/Integer;` nhưng giữ bootstrap trả String. Dự đoán `BootstrapMethodError` và cách kiểm tra một negative test.

**Bài 5 — Standard bootstrap:** Dùng `ConstantBootstraps.enumConstant` cho một enum do bạn tự định nghĩa, với descriptor của enum type. So sánh với `nullConstant` trong ví dụ.

**Bài 6 — Cùng source, hai loaders:** Dùng hai `ClassLoader` riêng định nghĩa hai class có cùng binary name và bytes. Giải thích runtime identity và resolution cache có độc lập không.

**Bài 7 — Concurrency:** Hai thread gọi method chứa `ldc` gần đồng thời. Assert các caller nhận kết quả đã được JVM chốt, **không** assert bootstrap invocation count chắc chắn bằng 1.

**Bài 8 — Transformer:** Viết ASM `MethodVisitor` phát hiện `ConstantDynamic` qua `visitLdcInsn`, in name/descriptor/bootstrap args nhưng **không invoke bootstrap**, rồi viết lại bytecode mà vẫn giữ semantics.

**Bài 9 — Compiler IR:** Chọn biểu diễn literal/condy/runtime expression cho: string cố định, VarHandle đã link, enum instance, feature flag, secret rotation và tạo đơn hàng. Giải thích lựa chọn.

### Checklist hoàn thành

- [ ] Hiểu **JEP 309** và `CONSTANT_Dynamic` có từ Java 11.
- [ ] Nhớ tag **17**, class-file version **55**, `BootstrapMethods` và field descriptor.
- [ ] Phân biệt condy với `invokedynamic` và `static final`.
- [ ] Biết bootstrap dùng `Lookup, String, Class` và optional static args.
- [ ] Biết `ConstantBootstraps` Java 11 và `java.lang.constant` ra đời sau.
- [ ] Chạy được `CondyAsmLab.java` với ASM 9.11.1 và `--release 11`.
- [ ] Kiểm tra `javap -v`, stdout và failure handling.
- [ ] Hiểu cache resolution, cache lỗi và bootstrap race.
- [ ] Thiết kế compiler/bytecode transformer không làm mất condy metadata.
- [ ] Không dùng condy cho side effect nghiệp vụ, config realtime hay secrets cần rotate.

## 19. Tài liệu tham khảo chính thức, vẫn áp dụng

1. [JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309): mục tiêu và feature Java 11.
2. [JVMS Java 11 — `4.4.10](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10): `CONSTANT_Dynamic_info` và `CONSTANT_InvokeDynamic_info`.
3. [JVMS Java 11 — `4.7.23](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23): `BootstrapMethods` attribute.
4. [JVMS Java 11 — `5.4.3.6](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6): resolution, static args, result validation, lỗi và concurrency.
5. [JVMS Java 11 — `ldc`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-6.html#jvms-6.5.ldc): instruction nạp runtime constant.
6. [Java SE 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): bootstrap chuẩn có từ Java 11.
7. [Java SE 11 — java.lang.invoke](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/package-summary.html): constant/call site resolution.
8. [OW2 ASM](https://asm.ow2.io/) và [ASM ConstantDynamic API](https://asm.ow2.io/javadoc/org/objectweb/asm/ConstantDynamic.html): phát/đọc dynamic constants.
9. [OW2 ASM release notes](https://asm.ow2.io/versions.html) và [Maven Central ASM](https://central.sonatype.com/artifact/org.ow2.asm/asm): xác nhận phiên bản 9.11.1.
10. [JEP 334 — JVM Constants API](https://openjdk.org/jeps/334): `java.lang.constant` từ Java 12.
11. [JEP 484 — Class-File API](https://openjdk.org/jeps/484): standard class-file tools có từ JDK 24, không phải Java 11.

**Tóm tắt:** `CONSTANT_Dynamic` cho phép compiler/thư viện bytecode biểu diễn một hằng số mà JVM gọi bootstrap để resolve khi cần. Hãy dùng ASM hoặc API bytecode được bảo trì, nhắm đúng version 55+, giữ name/descriptor/bootstrap/static args nhất quán, và kiểm tra bằng `javap` lẫn runtime tests. Resolution cache có giá trị cho hằng số late-bound, nhưng **không** biến condy thành state thay đổi liên tục hoặc đảm bảo side effect exactly-once.