# 14.2. Hợp đồng bootstrap hằng động: `Lookup`, tên và `Class<?>` của giá trị

## 1. Vì sao bootstrap của hằng động là một hợp đồng riêng?

**Hằng động (dynamically-computed constant, thường gọi là *condy*)** là một giá trị trong *runtime constant pool* được JVM phân giải bằng cách gọi một **bootstrap method**. Trong class file, nó được biểu diễn bởi `CONSTANT_Dynamic_info` (constant-pool tag **17**), xuất hiện từ class-file version **55.0 (Java 11)**.

Hợp đồng điển hình của bootstrap hằng là:

```java
public static Object bootstrap(
        MethodHandles.Lookup caller,
        String name,
        Class<?> type) throws Throwable {
    // Tính hoặc tìm giá trị tương thích với type rồi trả về.
    throw new UnsupportedOperationException("Illustration only");
}
```

Đây **chỉ là mẫu chữ ký API**, không phải ví dụ chạy độc lập. Khi thực thi một lệnh `ldc`/`ldc_w` tham chiếu `CONSTANT_Dynamic`, JVM giải quyết constant-pool entry, tạo các argument và gọi bootstrap. JVM kiểm tra giá trị trả về rồi lưu kết quả phân giải để những lần sử dụng cùng symbolic reference không phải tính lại.

Khác biệt quan trọng với **bootstrap của `invokedynamic`**:

```text
CONSTANT_Dynamic:
    bootstrap(Lookup, String, Class<?>, [static args...]) -> GIÁ TRỊ

CONSTANT_InvokeDynamic:
    bootstrap(Lookup, String, MethodType, [static args...]) -> CallSite
```

Hằng động có **field descriptor** và tạo **giá trị**; `invokedynamic` có **method descriptor** và liên kết **call site**. Ở bootstrap hằng, tham số thứ ba mang kiểu **`Class<?>` của giá trị**, **không phải `MethodType`**. Nhầm hai giao thức thường gây lỗi linkage.

Bài này giải thích đúng ý nghĩa từng tham số, dữ liệu đi từ class file đến bootstrap, cách kiểm tra kiểu và failure, đồng thời có ví dụ Java 17+ được kiểm chứng gồm **direct method call**, **hằng động thật được phát sinh trong class file**, và **các bootstrap chuẩn của JDK**.

## 2. Dữ liệu có sẵn trong `CONSTANT_Dynamic`

Một dynamic constant trong constant pool có cấu trúc logic:

```text
CONSTANT_Dynamic_info {
    tag = 17;
    bootstrap_method_attr_index;
    name_and_type_index;
}
```

`name_and_type_index` trỏ đến `CONSTANT_NameAndType_info` gồm:

- **Tên chưa được định danh đầy đủ (*unqualified name*)** của hằng, ví dụ `GREETING` hoặc `NUMBER`.
- **Field descriptor**, ví dụ `Ljava/lang/String;` cho `String`, `I` cho `int`, `[I` cho `int[]`.

`bootstrap_method_attr_index` trỏ đến một entry trong thuộc tính **`BootstrapMethods`** của chính class file chứa constant pool đó. Entry cho biết:

- **Method handle bootstrap** nào JVM cần resolve và gọi.
- **Zero hoặc nhiều static bootstrap arguments** nào sẽ đi kèm ba tham số mặc định.

Không có quy tắc rằng `GREETING` phải là một Java field tên `GREETING`. Ở đây tên là metadata của **constant-pool entry**, dùng cho bootstrap. Một `CONSTANT_Dynamic` hoàn toàn có thể không tương ứng với `static final` field nào trong source.

Ví dụ logic:

```text
Constant pool:
  #19 = Dynamic #0:GREETING:Ljava/lang/String;

BootstrapMethods:
  0: REF_invokeStatic CondyBootstrap.text:(Lookup,String,Class,String)Object
     Method arguments:
       "Hi, "

Code:
  0: ldc #19      // Dynamic #0:GREETING:Ljava/lang/String;
```

Đây là **bản rút gọn để giải thích cấu trúc**. Các descriptor/indices đầy đủ và bytecode thực tế có trong ví dụ `javap` ở mục 8. `#19` là chỉ số **constant pool**, `#0` là chỉ số **BootstrapMethods entry**; đừng nhầm hai loại index.

## 3. Tham số ngầm định thứ nhất: `MethodHandles.Lookup caller`

Với hằng động thật, JVM cung cấp `Lookup` có lookup class là **class mà runtime constant pool chứa symbolic reference đang được phân giải**. Trong ví dụ sau, class đó là `CondyClient`, vì `CondyClient.class` chứa `CONSTANT_Dynamic` và lệnh `ldc` dùng nó.

Bootstrap có thể hỏi:

```java
Class<?> requestingClass = caller.lookupClass();
```

Đoạn này **chỉ minh họa trong thân bootstrap**, nơi biến `caller` đã tồn tại.

Một vài tác dụng chính:

1. **Nhận diện ngữ cảnh**: biết class chứa hằng động là ai. `caller.lookupClass().getName()` có thể dùng để kiểm tra contract hoặc chẩn đoán.
2. **Phân quyền**: `Lookup` mang quyền truy cập của caller theo quy tắc Java/JPMS. Bootstrap có thể dùng `caller.findStatic`, `findGetter`, `findConstructor`, ... để tìm thành viên được phép truy cập.
3. **Không tự có mọi quyền**: `Lookup` không phải cơ chế vô hiệu hóa `private`, module readability, `exports` và `opens` cho toàn hệ thống.
4. **Không phải object gọi `ldc` gần nhất qua stack**: quyền của lookup gắn với **class tham chiếu dynamic constant**, không biến thành quyền của mỗi method hoặc thư viện tiếp tục gọi class ấy.

**Ràng buộc sâu trong JVMS 17:** đối với một `CONSTANT_Dynamic`, tham số **đầu tiên trong descriptor của bootstrap method handle phải là `java.lang.invoke.MethodHandles.Lookup`**, nếu không linkage thất bại với `BootstrapMethodError`. Đó là ràng buộc đặc biệt của condy; không nên suy rằng mọi tham số khác đều phải khớp cứng nhắc từng kiểu vì bootstrap được invoke theo cơ chế thích nghi tương đương `MethodHandle.invokeWithArguments`.

Với thiết kế mới, nên dùng chữ ký rõ ràng `(Lookup, String, Class<?>)` để dễ đọc và tránh các adaptation mơ hồ.

### Vì sao gọi bootstrap bằng Java trực tiếp không hoàn toàn tương đương?

Nếu code trong `CondyBootstrap.main` tự gọi:

```java
text(MethodHandles.lookup(), "GREETING", String.class, "Hi, ");
```

thì `Lookup.lookupClass()` là **`CondyBootstrap`**, vì đó là class thực sự gọi `MethodHandles.lookup()`. Trái lại, khi JVM resolve hằng trong `CondyClient.class`, `Lookup.lookupClass()` sẽ là **`CondyClient`**. Cùng một Java bootstrap method có thể nhận lookup context khác nhau theo đường đi.

Một lời gọi trực tiếp còn có thể thực hiện nhiều lần theo ý code Java; nó **không tự tạo `CONSTANT_Dynamic` hay `BootstrapMethods` trong class file**.

## 4. Tham số thứ hai: `String name`

`name` là **unqualified name** được lấy từ phần `NameAndType` của `CONSTANT_Dynamic`, ví dụ `GREETING` hoặc `NUMBER`.

Nó **không bắt buộc** là:

- Tên class chứa constant.
- Tên Java field.
- Tên phương thức bootstrap.
- Tên tham số trong source.
- Một tên được sinh từ stack trace tại runtime.

Bootstrap có thể **dùng** tên này để quyết định giá trị:

```java
return prefix + name;
```

Đây là **biểu thức minh họa** khi `prefix` và `name` đã có. Cũng có bootstrap cố ý bỏ qua `name`, ví dụ `ConstantBootstraps.nullConstant` không sử dụng tham số này.

Vì tên được ghi trong class file, nó thường ổn định đối với entry đang được resolve, nhưng **không phải dữ liệu do hệ thống xác thực người dùng**. Không nên dùng `name` làm bằng chứng caller đã được ủy quyền truy cập dữ liệu bí mật. Khi tên được sinh bởi toolchain/plugin không tin cậy, bootstrap cần xác nhận tên thuộc tập cho phép và kiểm tra `Lookup`/policy phù hợp.

### Tên, descriptor và bootstrap owner là ba dữ liệu khác nhau

Trong disassembly:

```text
Dynamic #0:GREETING:Ljava/lang/String;
```

- `#0` → **bootstrap specifier index**.
- `GREETING` → **name** truyền vào bootstrap.
- `Ljava/lang/String;` → **field descriptor**, quyết định `Class<?> type` là `String.class`.

Còn `CondyBootstrap.text` xuất hiện trong `BootstrapMethods` vì đó là **method handle bootstrap**; việc có `GREETING` không khiến JVM tìm Java method tên `GREETING`.

## 5. Tham số thứ ba: `Class<?> type` của **giá trị cần tạo**

Đây là phần cốt lõi của bài. Với `CONSTANT_Dynamic`, JVM biến field descriptor thành `Class<?>` tương ứng rồi chuyển cho bootstrap.

| Field descriptor | `Class<?> type` nhận được | Ví dụ giá trị hợp lệ |
| --- | --- | --- |
| `Ljava/lang/String;` | `String.class` | `"Hello"` |
| `Ljava/lang/Object;` | `Object.class` | Một reference bất kỳ, kể cả `null` |
| `I` | `int.class` | Giá trị primitive `int`; bootstrap có thể trả `Integer` để JVM unbox |
| `J` | `long.class` | Giá trị `long`, ví dụ bootstrap trả `Long` |
| `Z` | `boolean.class` | Boolean primitive, ví dụ trả `Boolean.TRUE` |
| `[I` | `int[].class` | Mảng `int[]` |
| `Ljava/time/DayOfWeek;` | `DayOfWeek.class` | `DayOfWeek.MONDAY` |

**Không dùng `type.getClass()` để xác định loại giá trị.** `type` vốn là một instance của `java.lang.Class`: `type.getClass()` thông thường trả `Class.class`. Muốn biết kiểu được mô tả, dùng `type == String.class`, `type == int.class`, `type.getName()`, `type.isPrimitive()`, `type.isArray()`.

Ví dụ validator trong bootstrap:

```java
if (type != String.class) {
    throw new IllegalArgumentException("Expected String constant");
}
return "configured";
```

Đây là **mảnh mã dùng trong thân bootstrap**, không phải class hoàn chỉnh. Với hằng có descriptor `I`, `type` là `int.class`, **không** phải `Integer.class`. Một bootstrap có return type `Object` vẫn có thể trả `Integer.valueOf(42)` rồi JVM chuyển kết quả sang primitive `int` theo hợp đồng linkage.

### Kiểm tra tương thích kết quả

Bootstrap của hằng động **trả một giá trị** (có thể khai báo Java return type `Object`), rồi JVM chuyển giá trị đó sang kiểu T của field descriptor:

- Nếu T là reference type `String`, giá trị phải là `String` tương thích hoặc `null`.
- Nếu T là primitive `int`, một `Integer` phù hợp có thể được unbox thành `int`; `null` không thể unbox.
- Nếu kết quả là reference sai kiểu (`String` nhưng T là `int`, hoặc `Integer` nhưng T là `String`), quá trình chuyển kiểu có thể gây `ClassCastException`; khi validation của condy thất bại bằng `ClassCastException`/`NullPointerException`, JVM báo **`BootstrapMethodError`**.
- **Không cần** bootstrap phải khai báo Java return type chính xác là kiểu T. Ví dụ method `public static Object number(...) { return 42; }` là phù hợp với một dynamic constant có descriptor `I`, vì autobox thành `Integer` rồi JVM unbox.
- Descriptor của hằng động là **field descriptor**, vì vậy **không thể là `V`/`void`** như kiểu trả về của một method.

JVM xử lý kết quả theo quy tắc conversion của đặc tả. Khi thiết kế bootstrap, nên **tự xác nhận kiểu đích và trả kết quả rõ ràng**, thay vì trông đợi conversion tình cờ thành công.

## 6. Ba tham số cố định và static bootstrap arguments

JVM tạo danh sách đối số theo thứ tự:

```text
0. Lookup caller
1. String name
2. Class<?> type          (đối với condy)
3. staticArgument0        (nếu có)
4. staticArgument1        (nếu có)
...
```

Chúng được dùng để gọi **bootstrap method handle** theo hành vi tương đương `invokeWithArguments`. Vì vậy chữ ký bootstrap phổ biến nhất là:

```java
public static Object bootstrap(
        MethodHandles.Lookup caller,
        String name,
        Class<?> type,
        String prefix) {
    return prefix + name;
}
```

Đây là mẫu method có **một static bootstrap argument** `String prefix`. Ở ví dụ thực hành, class generator gắn chuỗi `"Hi, "` vào `BootstrapMethods` entry, nên JVM truyền cho bootstrap bốn đối số khi resolve `GREETING`.

**Static bootstrap arguments không phải tham số truyền vào khi gọi `ldc`.** Chúng là metadata được ghi vào class file và được JVM resolve trước khi gọi bootstrap. Chúng có thể biểu diễn những loại constant-pool values được JVMS cho phép, gồm strings, numeric constants, class/method type/method handle references, và cả dynamic constants lồng nhau.

Ví dụ, một bootstrap nhận thêm `Class<?> owner` hoặc `MethodHandle factory` có thể sử dụng metadata đó để tìm dữ liệu; nhưng class generator phải tạo chính xác bootstrap specifier và các argument theo thứ tự mà method handle chấp nhận. Nếu số lượng/kiểu không thích hợp, resolution thất bại. Trường hợp bootstrap varargs được cho phép nhưng cũng cần tuân thủ các quy tắc method-handle invocation.

**Điểm không nên nói quá:** hợp đồng gọi bootstrap không bắt buộc Java method phải có chính xác dạng khai báo `(Lookup,String,Class<?>)Object` theo từng kiểu ở mọi vị trí. JVMS yêu cầu tham số đầu tiên của **condy bootstrap method handle** là `Lookup`; các tham số tiếp theo được chuyển với cơ chế adaptation. Trong code ứng dụng, giữ chữ ký chuẩn là thực hành dễ đọc và ít lỗi nhất.

### Nested condy và chu trình

Một static argument có thể bản thân là hằng động khác. JVM resolve argument này trước khi gọi bootstrap của hằng ngoài. Nhưng **không được có dependency cycle**, ví dụ hằng A cần A hoặc A cần B mà B lại cần A. JVMS 17 quy định resolution kiểu đó thất bại với `StackOverflowError` ở điểm phải resolve lại hằng đang chờ.

Vì vậy, đừng tạo bootstrap metadata có chu trình, và đừng thiết kế bootstrap chạy code quay lại chính hằng đang resolve mà không có cơ chế kết thúc.

## 7. Thực hành Java 17+ — phần A: định nghĩa bootstrap

Chúng ta sẽ dùng ba file:

```text
CondyBootstrap.java       // Java bootstrap methods hợp lệ
EmitCondyClient.java      // Công cụ thí nghiệm phát class file có CONSTANT_Dynamic thật
RunCondyClient.java       // Client chạy và quan sát linkage
```

File thứ hai dùng **`jdk.internal.org.objectweb.asm` có sẵn bên trong JDK** để thí nghiệm self-contained, không cần tải dependency ngoài. Đây là **internal API, không được hỗ trợ cho production**; phải thêm `--add-exports` khi biên dịch và chạy công cụ emitter. Trong ứng dụng thật, nên dùng thư viện **ASM chính thức** (`org.objectweb.asm`) hoặc bytecode library/framework được hỗ trợ thay vì phụ thuộc package `jdk.internal.*`. Thí nghiệm đã được kiểm tra trên JDK hỗ trợ Java 17; API nội bộ có thể thay đổi ở phiên bản JDK khác.

### File `CondyBootstrap.java`

```java
import java.lang.invoke.MethodHandles;

public final class CondyBootstrap {
    public static Object text(MethodHandles.Lookup caller,
                              String name, Class<?> type, String prefix) {
        System.out.println("bsmText:caller=" + caller.lookupClass().getSimpleName()
                + ",name=" + name + ",type=" + type.getSimpleName()
                + ",prefix=" + prefix);
        return prefix + name;
    }

    public static Object number(MethodHandles.Lookup caller,
                                String name, Class<?> type) {
        System.out.println("bsmNumber:caller=" + caller.lookupClass().getSimpleName()
                + ",name=" + name + ",type=" + type.getSimpleName());
        return 42;
    }

    public static Object wrong(MethodHandles.Lookup caller,
                               String name, Class<?> type) {
        System.out.println("bsmWrong:type=" + type.getSimpleName());
        return "not-an-int";
    }

    public static void main(String[] args) {
        Object answer = text(MethodHandles.lookup(), "GREETING",
                             String.class, "Hi, ");
        System.out.println("manual=" + answer);
    }
}
```

Các method thực hiện ba điều quan trọng:

- `text`: có tham số cố định `(Lookup, name, type)` cộng **một static argument `prefix`**; nó trả `String` nằm trong `Object`.
- `number`: trả `42`, được boxing thành `Integer`; khi hằng động có descriptor `I`, JVM chuyển sang primitive `int` thành công.
- `wrong`: cố tình trả `"not-an-int"` cho dynamic constant có descriptor `I`, dẫn tới **`BootstrapMethodError`** khi JVM validation kiểu kết quả.

`main` cho phép chạy **direct call** tới `text`. Đó là kiểm tra Java method thông thường, không phải con đường liên kết condy thật.

### Quan sát direct call

Chạy riêng:

```bash
javac --release 17 CondyBootstrap.java
java CondyBootstrap
```

Kết quả chính xác:

```text
bsmText:caller=CondyBootstrap,name=GREETING,type=String,prefix=Hi, 
manual=Hi, GREETING
```

Trong dòng đầu có **một dấu cách sau `Hi,`**: đó là phần đuôi của static argument `"Hi, "` trong log, không phải ký tự thừa do lỗi format. Direct call tự tạo `Lookup` trong `CondyBootstrap`, vì vậy `caller=CondyBootstrap`.

## 8. Thực hành Java 17+ — phần B: class file có `CONSTANT_Dynamic` thật

Java source thông thường không có cú pháp “viết một `CONSTANT_Dynamic` tùy ý” rồi yêu cầu `javac` phát constant-pool entry ấy. Ta dùng một bytecode emitter **chỉ trong bài thực hành** để tạo class `CondyClient` với ba static methods:

```text
CondyClient.readText()    -> ldc Dynamic GREETING:Ljava/lang/String;
CondyClient.readNumber()  -> ldc Dynamic NUMBER:I
CondyClient.readBad()     -> ldc Dynamic BAD:I
```

Tất cả method được tạo thành bytecode trực tiếp, không có source file `CondyClient.java`. Điều này giúp **phân biệt tuyệt đối** giữa việc tự gọi Java bootstrap và việc JVM resolve hằng động thật.

### File `EmitCondyClient.java` (công cụ thí nghiệm nội bộ JDK)

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import jdk.internal.org.objectweb.asm.ClassWriter;
import jdk.internal.org.objectweb.asm.ConstantDynamic;
import jdk.internal.org.objectweb.asm.Handle;
import jdk.internal.org.objectweb.asm.MethodVisitor;
import jdk.internal.org.objectweb.asm.Opcodes;

public final class EmitCondyClient implements Opcodes {
    public static void main(String[] args) throws IOException {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(V17, ACC_PUBLIC | ACC_SUPER, "CondyClient",
                 null, "java/lang/Object", null);

        Handle textBsm = new Handle(H_INVOKESTATIC, "CondyBootstrap", "text",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
                        + "Ljava/lang/Class;Ljava/lang/String;)Ljava/lang/Object;",
                false);
        Handle intBsm = new Handle(H_INVOKESTATIC, "CondyBootstrap", "number",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
                        + "Ljava/lang/Class;)Ljava/lang/Object;",
                false);
        Handle wrongBsm = new Handle(H_INVOKESTATIC, "CondyBootstrap", "wrong",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
                        + "Ljava/lang/Class;)Ljava/lang/Object;",
                false);

        addLdcMethod(cw, "readText", "()Ljava/lang/String;",
                new ConstantDynamic("GREETING", "Ljava/lang/String;",
                                    textBsm, "Hi, "), ARETURN);
        addLdcMethod(cw, "readNumber", "()I",
                new ConstantDynamic("NUMBER", "I", intBsm), IRETURN);
        addLdcMethod(cw, "readBad", "()I",
                new ConstantDynamic("BAD", "I", wrongBsm), IRETURN);

        cw.visitEnd();
        Files.write(Path.of("CondyClient.class"), cw.toByteArray());
    }

    private static void addLdcMethod(ClassWriter cw, String name,
                                     String descriptor, ConstantDynamic constant,
                                     int returnOpcode) {
        MethodVisitor mv = cw.visitMethod(
                ACC_PUBLIC | ACC_STATIC, name, descriptor, null, null);
        mv.visitCode();
        mv.visitLdcInsn(constant);
        mv.visitInsn(returnOpcode);
        mv.visitMaxs(1, 0);
        mv.visitEnd();
    }
}
```

**Chú ý giới hạn thực hành:** ví dụ sử dụng package ASM nội bộ của JDK chỉ để tự tạo class file trên môi trường học, với hai flags `--add-exports`. Đây **không phải lời khuyên triển khai production**. Nếu dùng ASM chính thức, các kiểu tương đương nằm trong `org.objectweb.asm` và phải khai báo dependency, chọn phiên bản tương thích class-file version.

Giải thích các dòng trọng tâm:

1. `cw.visit(V17,...)` tạo class-file version **61**, có hỗ trợ condy (cần ít nhất version 55).
2. `new Handle(H_INVOKESTATIC, "CondyBootstrap", "text", ... )` tạo **bootstrap method handle** tới Java static method. Descriptor ghi **`Lookup, String, Class, String -> Object`**.
3. `new ConstantDynamic("GREETING", "Ljava/lang/String;", textBsm, "Hi, ")` tạo một symbolic dynamic constant: **name**, **field descriptor**, **bootstrap method** và **một static bootstrap argument**.
4. `mv.visitLdcInsn(constant)` phát instruction `ldc` tham chiếu constant-pool entry động.
5. `ARETURN` là opcode trả về object reference cho `readText`; `IRETURN` trả primitive `int` cho `readNumber` và `readBad`.
6. `Files.write(...)` xuất `CondyClient.class`; công cụ không cần tạo `CondyClient.java`.
7. Với condy kiểu `long` hoặc `double`, opcode tải phù hợp là `ldc2_w`, không dùng `ldc` một slot như `String`/`int`. Bộ emitter cần chọn đúng kind/stack size; ví dụ này chỉ dùng `String` và `int`.

Một `ConstantDynamic` do ASM biểu diễn là **metadata dùng để phát class file**; bản thân object ASM này **không phải** giá trị runtime mà JVM trả cho `ldc`.

### File `RunCondyClient.java`

```java
public final class RunCondyClient {
    public static void main(String[] args) {
        System.out.println("first=" + CondyClient.readText());
        System.out.println("second=" + CondyClient.readText());
        System.out.println("number=" + CondyClient.readNumber());

        for (int i = 0; i < 2; i++) {
            try {
                System.out.println("bad=" + CondyClient.readBad());
            } catch (BootstrapMethodError failure) {
                System.out.println("badFailure="
                        + failure.getClass().getSimpleName());
            }
        }
    }
}
```

`RunCondyClient` là một Java source file độc lập **nhưng phụ thuộc `CondyClient.class` vừa được emitter tạo**. Hãy tạo đủ file và chạy theo đúng thứ tự ở mục tiếp theo; không được biên dịch `RunCondyClient.java` trước khi chạy emitter.

## 9. Lệnh chạy theo thứ tự và kết quả đã kiểm chứng

Đặt ba file source cùng thư mục và dùng JDK 17 trở lên. Các lệnh sau không yêu cầu Maven/Gradle:

```bash
javac --release 17 CondyBootstrap.java

javac --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED EmitCondyClient.java
java --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED EmitCondyClient

javac --release 17 RunCondyClient.java

java CondyBootstrap
java RunCondyClient
```

Giải thích:

- `CondyBootstrap.java` và `RunCondyClient.java` sử dụng API Java công khai nên biên dịch được với `--release 17`.
- `EmitCondyClient.java` phải dùng `--add-exports` khi **biên dịch lẫn chạy** vì dùng package nội bộ. Không kết hợp `--release 17` với `--add-exports` dành cho internal API trong lệnh biên dịch emitter.
- File được tạo có tên `CondyClient.class` và class-file version **61** do `V17`; khi biên dịch `RunCondyClient`, `javac` tìm thấy class file ấy trên classpath hiện tại.
- `java RunCondyClient` không cần `--add-exports`: **class runtime và bootstrap không phụ thuộc ASM**. Emitter đã hoàn thành nhiệm vụ trước khi chạy.

### 9.1. `java CondyBootstrap`: direct call

```text
bsmText:caller=CondyBootstrap,name=GREETING,type=String,prefix=Hi, 
manual=Hi, GREETING
```

### 9.2. `java RunCondyClient`: resolve hằng động thật

```text
bsmText:caller=CondyClient,name=GREETING,type=String,prefix=Hi, 
first=Hi, GREETING
second=Hi, GREETING
bsmNumber:caller=CondyClient,name=NUMBER,type=int
number=42
bsmWrong:type=int
badFailure=BootstrapMethodError
badFailure=BootstrapMethodError
```

Các kết quả trên đã được kiểm chứng với chương trình Java 17 và class file do emitter tạo.

### Phân tích từng hiện tượng

**`caller=CondyClient`**: bootstrap không được gọi từ `CondyBootstrap.main`, mà JVM đang resolve symbolic reference trong runtime constant pool của class `CondyClient`. `Lookup` được tạo theo ngữ cảnh đó.

**`name=GREETING`, `type=String`**: JVM lấy name từ `CONSTANT_NameAndType` và biến field descriptor `Ljava/lang/String;` thành `String.class`, chứ không gửi `MethodType` hay `String.class.getClass()`.

**`prefix=Hi, `**: đây là static bootstrap argument được ghi trong class file. `RunCondyClient` **không** truyền `prefix` vào `readText()`; method đó không có tham số.

**`second=...` nhưng không có `bsmText` lần hai**: cùng symbolic reference đã được resolve thành công và kết quả được dùng lại. Trong thí nghiệm tuần tự này, bootstrap chỉ chạy một lần cho entry `GREETING`.

**`bsmNumber:...type=int`**: field descriptor `I` làm `type == int.class`; bootstrap `number` trả `Integer` từ boxing `42`, JVM unbox về primitive `int`, nên `number=42`.

**`bsmWrong` xuất hiện một lần**: bootstrap trả `String` cho descriptor `I`; validation result thất bại và JVM ném `BootstrapMethodError`. Lần dùng tiếp cùng reference vẫn thất bại; không chạy bootstrap thêm lần nữa trong thí nghiệm tuần tự này.

**Hai dòng `badFailure=BootstrapMethodError`** chứng minh failure được ghi nhận ở quá trình resolution của dynamic constant, chứ không phải một Java `ClassCastException` tình cờ xuất hiện ở `RunCondyClient`.

## 10. Kiểm tra class file bằng `javap -c -v -p`

Chạy:

```bash
javap -p -c -v CondyClient
```

Trong kết quả của class đã kiểm chứng, có các dòng tiêu biểu:

```text
major version: 61

#19 = Dynamic #0:#18        // #0:GREETING:Ljava/lang/String;
#30 = Dynamic #1:#29        // #1:NUMBER:I
#38 = Dynamic #2:#37        // #2:BAD:I

0: ldc #19                  // Dynamic #0:GREETING:Ljava/lang/String;
0: ldc #30                  // Dynamic #1:NUMBER:I
0: ldc #38                  // Dynamic #2:BAD:I

BootstrapMethods:
  0: REF_invokeStatic CondyBootstrap.text:...
  1: REF_invokeStatic CondyBootstrap.number:...
  2: REF_invokeStatic CondyBootstrap.wrong:...
```

Ở đây đoạn hiển thị được **rút gọn có chủ đích**: dấu `...` thay thế JVM descriptors đầy đủ và các hằng định danh constant pool; đây **không phải một đoạn `javap` hoàn chỉnh để copy chạy**. Số `#19`, `#30`, `#38` là của một lần kiểm thử cụ thể và có thể khác theo toolchain. Mỗi dòng `0: ldc ...` thuộc **một method khác nhau**, nên cả ba đều có bytecode offset `0`.

Điểm cần kiểm tra trong một bản disassembly thật:

1. Có `Dynamic` (tag 17), **không phải `InvokeDynamic` (tag 18)**, tại các constant-pool entries chứa `GREETING`, `NUMBER`, `BAD`.
2. Mỗi `Dynamic` ghi **field descriptor** (`Ljava/lang/String;`, `I`).
3. `Code` chứa **`ldc`** tham chiếu tới các `Dynamic` entry.
4. Có một **`BootstrapMethods` attribute** chứa **ba entries** với method handles trỏ tới `CondyBootstrap.text`, `CondyBootstrap.number`, `CondyBootstrap.wrong`.
5. Entry của `text` còn có một static argument: `"Hi, "`.
6. Class có major version `61`, ứng với Java 17.

**Không cần opcode `invokedynamic` để dùng hằng động**. Đây là bẫy đọc bytecode: `CONSTANT_Dynamic` thông thường được nạp qua `ldc`, còn `CONSTANT_InvokeDynamic` được sử dụng bởi instruction `invokedynamic`. Cả hai chia sẻ cơ chế bootstrap metadata nhưng tạo **loại kết quả khác nhau**.

## 11. Thời điểm resolve, cache và đa luồng

Với một `CONSTANT_Dynamic` chưa resolve, JVM có thể tính giá trị khi thực hiện instruction cần hằng lần đầu. Sau khi resolve thành công:

- Kết quả được lưu cho **symbolic reference trong runtime constant pool**.
- Những lần dùng tiếp cùng symbolic reference nhận kết quả đã resolve, **không chạy bootstrap lặp lại**.
- Nếu giá trị là reference tới một object mutable, việc “constant” **không** biến object đó thành immutable. Mọi code giữ reference vẫn có thể làm thay đổi nội dung object nếu class/API của object cho phép.
- Nếu resolve thất bại, những lần dùng tiếp cùng reference tiếp tục nhận lỗi theo quy tắc JVMS; không coi lời gọi tiếp như một cơ hội tự thử lại bootstrap.
- Không nhầm scope lưu kết quả của một runtime constant-pool entry với “cache toàn JVM theo tên hằng”. Hai class/constant-pool entries khác nhau có thể dùng cùng name/type nhưng là symbolic references khác nhau.

**Điểm cần chú ý về concurrency:** nếu nhiều thread đồng thời cố resolve cùng một reference chưa được giải quyết, JVMS cho phép bootstrap method handle được **invoke đồng thời**. JVM chọn một kết quả và cài đặt công khai cho các thread; các kết quả bootstrap khác có thể bị bỏ qua. Vì thế không nên dựa vào phát biểu tuyệt đối “Java bootstrap method sẽ chỉ thực thi đúng một lần dù có race”.

Bootstrap có side effect nên được thiết kế thread-safe, hoặc idempotent khi cần. Trong ví dụ ở mục 9, các lời gọi thực hiện **tuần tự**, vì vậy quan sát một lần bootstrap là phù hợp và có thể lặp lại.

### 11.1. Hằng động có thể là `null`

Reference-type condy có thể resolve thành **`null`** hợp lệ. Đây không phải lỗi bootstrap nếu field descriptor là reference. Ngược lại, với primitive descriptor như `I`, `null` không thể unbox và làm resolution thất bại.

Đặc tả không đòi đối tượng `String`/class mới được tạo mỗi lần `ldc`: trong cùng symbolic reference, một giá trị đã được resolve được tái sử dụng; `null` cũng là giá trị có thể được tái sử dụng cho reference type.

## 12. Bootstrap hằng chuẩn có sẵn: `ConstantBootstraps`

Java 11+ cung cấp `java.lang.invoke.ConstantBootstraps` trong module `java.base`. Nó tập hợp các bootstrap methods tiêu chuẩn; một số có thể được tham chiếu bởi bytecode generator thay vì bạn phải tự viết bootstrap từ đầu.

Ví dụ điển hình:

| API chuẩn | Ý nghĩa | Tham số liên quan |
| --- | --- | --- |
| `nullConstant` | Trả `null` cho reference type | `type` phải là reference type |
| `primitiveClass` | Trả `Class<?>` của primitive dựa vào descriptor trong `name` | `name` như `"I"`; `type` phải là `Class.class` |
| `enumConstant` | Trả enum constant dựa vào tên và loại enum | `name` như `"MONDAY"`; `type` như `DayOfWeek.class` |
| `getStaticFinal` | Lấy giá trị static-final field hợp lệ | `name`, `type`, đôi khi class khai báo |
| `fieldVarHandle`, `staticFieldVarHandle`, `arrayVarHandle` | Tạo `VarHandle` phù hợp | `Lookup` và các metadata về field/array |
| `explicitCast` | Chuyển một giá trị sang loại được yêu cầu | `Class<?> dstType` và static argument |
| `invoke` | Gọi một `MethodHandle` với những static arguments | `type`, method handle và args |

Một số API **cố tình bỏ qua** `lookup`/`name`, một số API **dùng chúng** để tra cứu metadata hoặc kiểm tra quyền. Đừng cho rằng mọi bootstrap chuẩn đều diễn giải `name` theo một cách.

### Ví dụ Java 17+ thứ hai — sử dụng API chuẩn trực tiếp

Lưu file **`ConstantBootstraps17Demo.java`**:

```java
import java.lang.invoke.ConstantBootstraps;
import java.lang.invoke.MethodHandles;
import java.time.DayOfWeek;

public final class ConstantBootstraps17Demo {
    public static void main(String[] args) {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Object blank = ConstantBootstraps.nullConstant(
                lookup, "IGNORED", String.class);
        System.out.println("null=" + (blank == null));

        DayOfWeek day = ConstantBootstraps.enumConstant(
                lookup, "MONDAY", DayOfWeek.class);
        System.out.println("enum=" + day);

        Class<?> ptype = ConstantBootstraps.primitiveClass(
                lookup, "I", Class.class);
        System.out.println("primitive=" + ptype);

        try {
            ConstantBootstraps.nullConstant(lookup, "WRONG", int.class);
            System.out.println("primitiveNull=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("primitiveNull=rejected");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ConstantBootstraps17Demo.java
java ConstantBootstraps17Demo
```

Kết quả đã kiểm chứng:

```text
null=true
enum=MONDAY
primitive=int
primitiveNull=rejected
```

**Quan trọng:** đoạn code này **gọi các bootstrap standard bằng Java trực tiếp**, nên là ví dụ kiểm tra behavior của API, **không phải** chứng cứ class này chứa `CONSTANT_Dynamic` thực. Muốn JVM dùng các API trên để link condy, phải để bytecode generator/compiler tham chiếu tới chúng trong `BootstrapMethods`.

Riêng `primitiveClass(lookup, "I", Class.class)` thể hiện rõ **`name` có thể mang descriptor của primitive** theo contract của bootstrap chuẩn ấy, trong khi kết quả của hằng được yêu cầu có type **`Class.class`**. `Class<?> type` không phải kiểu primitive trong trường hợp này, dù giá trị trả về là `int.class`.

## 13. Điều gì xảy ra nếu bootstrap sai hợp đồng?

Các lỗi dễ nhầm:

### 13.1. Tham số thứ ba sai: dùng `MethodType` thay vì `Class<?>`

Nếu bytecode mô tả một condy, JVM chuẩn bị một `Class<?>` lấy từ **field descriptor**. Bootstrap được viết như thể đang nhận `MethodType` của `invokedynamic` có thể không nhận được đối số tương thích, gây lỗi **khi invoke bootstrap method handle**. Kết quả là linkage failure, thường hiện ra dưới dạng `BootstrapMethodError` nếu lỗi invocation không thuộc loại `Error` trực tiếp.

Phòng ngừa: viết chữ ký chuẩn `(Lookup,String,Class<?>)` cho condy. Chỉ dùng `MethodType` ở giao thức bootstrap **call site** hoặc khi đó là static argument riêng mà bạn thiết kế.

### 13.2. Bootstrap trả `CallSite` thay vì giá trị

`CONSTANT_Dynamic` mong một **giá trị có thể chuyển thành kiểu T**, không mong `CallSite`. Nếu `type == String.class` mà bootstrap trả một `ConstantCallSite`, kết quả không phù hợp với `String`, nên validation thất bại.

Trường hợp đặc biệt: nếu field descriptor là `Ljava/lang/Object;`, một object `CallSite` cũng là một `Object` có thể hợp lệ **như một giá trị**; nhưng điều đó **không biến** hằng thành `invokedynamic`. JVM sẽ chỉ coi `CallSite` đó là object được nạp qua `ldc`.

### 13.3. Bootstrap trả `String` cho descriptor `I`

Ví dụ `wrong` trong mục 7–9 đã chứng minh:

```text
bsmWrong:type=int
badFailure=BootstrapMethodError
```

Lỗi không nằm ở tên `BAD` mà nằm ở **sự không tương thích kiểu kết quả**. JVM biết type từ descriptor `I`, không suy type từ object runtime mà bootstrap trả.

### 13.4. Primitive hằng nhưng trả `null`

`null` hợp lệ cho reference descriptors như `Ljava/lang/String;`; không hợp lệ khi type đích là primitive. Validation sẽ thất bại do unboxing `null`, thường được báo thành `BootstrapMethodError`.

### 13.5. Method handle bootstrap không gọi được hoặc `Lookup` không đủ quyền

Để resolve hằng, JVM phải resolve bootstrap method handle và các static arguments theo quy tắc class-file access. Khi bootstrap tự tìm field/method private, `Lookup` không được bỏ qua JPMS và Java visibility. Những lỗi xảy ra khi resolve hoặc invoke method handle có thể biểu hiện dưới nhiều loại linkage/error theo đặc tả; không phải lúc nào cũng là `ClassCastException`.

Nên kiểm tra **bootstrap owner**, descriptors, class loader/module graph và quyền của `caller.lookupClass()` trước khi kết luận phương thức `bootstrap` bị viết sai.

### 13.6. Bootstrap ném exception

Theo JVMS 17 §5.4.3.6, nếu bootstrap invocation ném một **`Error`**, resolution thất bại với error đó. Nếu ném exception **không thuộc nhánh `Error`**, JVM tạo `BootstrapMethodError` và giữ exception gốc làm cause. Nếu lỗi xảy ra trong bước kiểm tra kiểu trả về, `ClassCastException`/`NullPointerException` cũng làm resolution báo `BootstrapMethodError`.

Điều này khác với **gọi Java bootstrap thủ công**: direct call vẫn tuân theo exception do Java method tự ném và không tự có bước JVM validation của `CONSTANT_Dynamic`.

## 14. Bảng đối chiếu `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic`

| Thuộc tính | Hằng động — condy | Lời gọi động — indy |
| --- | --- | --- |
| Constant-pool tag | **17 — `CONSTANT_Dynamic`** | **18 — `CONSTANT_InvokeDynamic`** |
| NameAndType descriptor | **Field descriptor** (`I`, `Ljava/lang/String;`, ...) | **Method descriptor** (`(I)Ljava/lang/String;`, ...) |
| Tham số thứ nhất bootstrap thường là | `MethodHandles.Lookup` của class chứa reference; với condy bootstrap BMH, first parameter phải là Lookup | `MethodHandles.Lookup` của caller theo giao thức thường dùng |
| Tham số thứ hai | `String name` | `String name` |
| Tham số thứ ba | **`Class<?> type`** | **`MethodType type`** |
| Kết quả yêu cầu | Giá trị tương thích với field descriptor | `CallSite` có target type khớp method descriptor |
| Opcode tiêu biểu | **`ldc` / `ldc_w`**, `ldc2_w` với kiểu hai slot | **`invokedynamic`** |
| BootstrapMethods attribute | Có khi constant pool dùng `CONSTANT_Dynamic` | Có khi constant pool dùng `CONSTANT_InvokeDynamic` |
| Cache linkage thành công | Theo symbolic reference trong runtime constant pool | Theo instruction được resolve |
| Từ Java source thông thường | Không có cú pháp trực tiếp cho custom `CONSTANT_Dynamic` | Java compiler có thể tự phát qua lambda/method reference/string concat |
| Lỗi đáng chú ý | Sai kiểu kết quả, thiếu quyền, chu trình static args, bootstrap failure | `CallSite` sai/null/target type mismatch, bootstrap failure |

`BootstrapMethods` có thể phục vụ **cả hai** loại constant-pool entries, do đó chỉ nhìn thấy thuộc tính này không cho biết class đang dùng condy hay indy. Muốn xác minh, phải đọc **constant-pool tag**, **NameAndType descriptor**, instruction sử dụng và bootstrap entry tương ứng.

## 15. Những ngộ nhận cần loại bỏ

1. **“Bootstrap tên `bootstrap` được JVM tự tìm theo tên.”** Sai: class-file metadata chọn method handle bootstrap cụ thể; tên Java method là tùy tác giả.
2. **“`name` là tên của static field.”** Không bắt buộc. Nó là unqualified name của condy entry.
3. **“Tham số thứ ba luôn là `MethodType`.”** Sai đối với condy: JVM cung cấp `Class<?>` của giá trị.
4. **“`type == Integer.class` nếu descriptor là `I`.”** Sai: đó là `int.class`.
5. **“Bootstrap `Object` return type không hợp lệ cho hằng `int`.”** Sai: JVM có thể chuyển wrapper tương thích sang primitive, như demo `42`.
6. **“`ConstantCallSite` là bắt buộc cho condy.”** Sai: condy cần **giá trị**; `CallSite` là kết quả cần cho invokedynamic.
7. **“Đã gọi `CondyBootstrap.text` bằng Java nên class có condy.”** Sai: direct method call không phát `CONSTANT_Dynamic`.
8. **“Mọi lần `ldc` đều gọi bootstrap lại.”** Sai sau khi cùng symbolic reference được resolve thành công.
9. **“Bootstrap chắc chắn chỉ chạy đúng một lần trong mọi race.”** Không tuyệt đối; nhiều thread có thể invoke bootstrap đồng thời trước khi JVM chọn kết quả resolution.
10. **“Hằng động bảo đảm object được trả về immutable.”** Sai: kết quả có thể là một mutable object; việc constant resolution chỉ bảo đảm cơ chế lưu giá trị cho symbolic reference.
11. **“Có `BootstrapMethods` là class đã dùng `invokedynamic`.”** Sai: attribute cũng chứa bootstrap specifiers cho `CONSTANT_Dynamic`.
12. **“`null` luôn là bootstrap failure.”** Sai nếu type đích là reference; đúng là không thể unbox `null` thành primitive.
13. **“Có thể đặt `void.class` làm type của một condy.”** Không: field descriptor không biểu diễn `void`.
14. **“Muốn kiểm tra condy chỉ cần nhìn stdout.”** Không: stdout chứng minh method chạy, nhưng không chứng minh JVM đã resolve `CONSTANT_Dynamic`; cần `javap -v`.
15. **“Được trả `Lookup` là có thể đọc mọi private field.”** Sai: quyền của lookup gắn với caller/JPMS và quy tắc Java access.

## 16. Checklist debug một bootstrap hằng động

Khi ứng dụng báo `BootstrapMethodError` hoặc có hằng động giá trị sai:

1. **Chọn đúng class file đang chạy** và dùng `javap -p -c -v` để lấy bytecode thật.
2. **Tìm constant-pool tag `Dynamic`**, không nhầm `InvokeDynamic`.
3. **Đọc name và field descriptor**; đổi descriptor sang kiểu `Class<?>` mong đợi (`I` → `int.class`, `Ljava/lang/String;` → `String.class`).
4. **Tìm bootstrap entry** qua `bootstrap_method_attr_index`; xác nhận owner/name/descriptor của bootstrap method handle.
5. **Kiểm tra tham số đầu** của bootstrap method handle là `MethodHandles.Lookup` theo ràng buộc JVMS dành cho condy.
6. **Kiểm tra thứ tự static args** sau `Lookup, String, Class<?>`: có thiếu, sai loại hoặc hoán đổi thứ tự không?
7. **Xác minh khả năng truy cập bootstrap**: class loader, Java visibility và JPMS module permissions.
8. **Kiểm tra code sử dụng `caller`**: `caller.lookupClass()` có đúng class chứa condy không? Direct Java call và JVM condy resolution có thể khác nhau.
9. **Kiểm tra kiểu kết quả thực**: reference cast, boxing/unboxing primitive, và `null` có hợp lệ với descriptor không?
10. **Nếu lỗi liên quan cycle**, kiểm tra static arguments tham chiếu các condy entry khác theo chu trình hoặc bootstrap gọi lại chính constant đang resolve.
11. **Phân biệt lỗi lần đầu và lỗi được ghi nhớ**: thất bại khi resolve cùng symbolic reference không tự được reset bởi lời gọi tiếp.
12. **Kiểm tra concurrency** nếu bootstrap dùng cache, counter, logging hoặc tài nguyên bên ngoài.
13. **Đọc cause của `BootstrapMethodError`** và stack trace của method handle/bootstrap; không xóa thông tin gốc.
14. **Không kết luận chỉ từ một dòng log**: disassembly mới cho biết đây là Java direct call hay runtime dynamic-constant resolution.

## 17. Câu hỏi tự kiểm tra (có đáp án)

1. **Ba tham số đầu bootstrap condy là gì?** `MethodHandles.Lookup`, `String name`, `Class<?> type`.
2. **Cặp thông tin nào quyết định `name` và `type`?** `NameAndType` của `CONSTANT_Dynamic`: unqualified name + field descriptor.
3. **Nếu descriptor là `I` thì JVM truyền `type` nào?** `int.class`.
4. **Nếu descriptor là `Ljava/lang/String;`?** `String.class`.
5. **Bootstrap `Object number(...) { return 42; }` có thể phục vụ condy `I` không?** Có, thông qua `Integer` boxing và JVM unboxing hợp lệ.
6. **Bootstrap `Object wrong(...) { return "x"; }` phục vụ condy `I` thì sao?** Validation kiểu thất bại, có thể thành `BootstrapMethodError`; đã kiểm chứng.
7. **`caller.lookupClass()` lấy từ đâu khi resolve condy thật?** Class chứa runtime constant-pool symbolic reference đang được resolve.
8. **`name` có bắt buộc trùng Java field nào không?** Không.
9. **Static bootstrap argument nằm ở đâu?** Trong `BootstrapMethods` entry được class-file metadata chỉ định.
10. **Static args có được truyền sau ba tham số JVM tạo không?** Có, theo thứ tự ghi trong bootstrap specifier.
11. **Kết quả bootstrap condy có phải `CallSite` không?** Không bắt buộc và không phải contract; đây là **giá trị** tương thích với field descriptor.
12. **Với invokedynamic, tham số thứ ba thường là gì?** `MethodType`, vì call site có method descriptor.
13. **Muốn xác minh condy thật, tìm opcode nào?** Thường `ldc`/`ldc_w` (và `ldc2_w` cho kiểu hai slot), kèm `CONSTANT_Dynamic` và `BootstrapMethods`.
14. **`BootstrapMethods` có thể tồn tại dù không có opcode `invokedynamic` không?** Có, nó cũng phục vụ condy.
15. **Dùng `ConstantBootstraps.nullConstant(..., String.class)` trả `null` có hợp lệ không?** Có, vì `String` là reference type.
16. **Dùng `nullConstant(..., int.class)` thì sao?** API chuẩn từ chối vì `int` là primitive.
17. **Nếu hai lần liên tiếp dùng cùng condy symbolic reference, bootstrap có chạy lại không?** Không sau resolution thành công; trong demo tuần tự chỉ có một log bootstrap.
18. **Trong race, có thể có nhiều bootstrap invocations không?** Có; JVM chọn kết quả resolution, nên bootstrap cần xử lý concurrency khi có side effect.
19. **Vì sao bài có file emitter?** Java source bình thường không thể chỉ định custom `CONSTANT_Dynamic`; phải tạo bytecode hoặc dùng công cụ biên dịch hỗ trợ.
20. **Lỗi lớn nhất khi viết bootstrap condy bằng cách sao chép code invokedynamic là gì?** Dùng `MethodType` và trả `CallSite` thay vì nhận `Class<?>` và trả giá trị đúng kiểu.

## 18. Tài liệu chuẩn Java SE 17 / JVMS 17

- [JVMS 17 — §4.4.10 `CONSTANT_Dynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10): cấu trúc constant-pool, field descriptor và bootstrap index.
- [JVMS 17 — §4.7.23 `BootstrapMethods`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23): bootstrap method handles và static arguments.
- [JVMS 17 — §5.4.3.6](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): quy trình resolve, truyền `Lookup/name/Class`, kiểm tra kết quả, lỗi và concurrency.
- [JVMS 17 — §6.5 `ldc` / `ldc_w` / `ldc2_w`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.ldc): tải giá trị từ runtime constant pool.
- [Java SE 17 — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): các bootstrap methods chuẩn cho dynamically-computed constants.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup class, quyền truy cập, phương thức tạo handle.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): đọc class file ở cấp instruction, constant pool và attributes.

**Kết luận:** Với **`CONSTANT_Dynamic`**, JVM gọi bootstrap bằng ngữ cảnh **`Lookup caller`**, **`String name`** và **`Class<?> type` của field descriptor**, cộng static bootstrap arguments nếu có; bootstrap phải cho ra **một giá trị tương thích** với type. Nắm chắc ba tham số này sẽ giúp bạn phân biệt condy với `invokedynamic`, thiết kế bootstrap đúng contract, hiểu caching và truy ngược lỗi qua bytecode thật.